import type { IExecuteFunctions, INodeExecutionData, INodeType, INodeTypeDescription } from 'n8n-workflow';
import axios from 'axios';

/**
 * TikTok Content Posting API - Direct Post.
 * Docs: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
 *
 * Two sources:
 *  - PULL_FROM_URL: TikTok downloads the MP4 from a URL (the URL's domain must be verified in your TikTok app).
 *  - FILE_UPLOAD:   we PUT the binary ourselves (single chunk up to 64 MB) - no domain verification needed.
 *
 * Notes: unaudited apps can only post with privacy_level SELF_ONLY until the app passes TikTok's audit.
 * The access token needs the `video.publish` scope (and `video.upload` for FILE_UPLOAD).
 */
const API = 'https://open.tiktokapis.com/v2';

export class TikTokPost implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'TikTok Post',
    name: 'tikTokPost',
    icon: 'fa:video',
    group: ['output'],
    version: 1,
    description: 'Publish a video to TikTok via the Content Posting API (init → upload → status)',
    defaults: { name: 'TikTok Post' },
    inputs: ['main'],
    outputs: ['main'],
    properties: [
      { displayName: 'Access Token', name: 'accessToken', type: 'string', typeOptions: { password: true }, default: '', required: true, description: 'User access token with video.publish (+ video.upload for binary) scopes' },
      {
        displayName: 'Source', name: 'source', type: 'options', default: 'FILE_UPLOAD',
        options: [
          { name: 'Binary (upload from n8n)', value: 'FILE_UPLOAD' },
          { name: 'Pull from URL (verified domain)', value: 'PULL_FROM_URL' },
        ],
      },
      { displayName: 'Video Binary Property', name: 'binaryProperty', type: 'string', default: 'data', displayOptions: { show: { source: ['FILE_UPLOAD'] } } },
      { displayName: 'Video URL', name: 'videoUrl', type: 'string', default: '', displayOptions: { show: { source: ['PULL_FROM_URL'] } } },
      { displayName: 'Caption', name: 'caption', type: 'string', typeOptions: { rows: 4 }, default: '', description: 'Max 2200 chars; #hashtags and @mentions allowed' },
      {
        displayName: 'Privacy', name: 'privacy', type: 'options', default: 'SELF_ONLY',
        options: [
          { name: 'Private (SELF_ONLY) - required until app is audited', value: 'SELF_ONLY' },
          { name: 'Public', value: 'PUBLIC_TO_EVERYONE' },
          { name: 'Friends', value: 'MUTUAL_FOLLOW_FRIENDS' },
          { name: 'Followers', value: 'FOLLOWER_OF_CREATOR' },
        ],
      },
      { displayName: 'Disable Comments', name: 'disableComment', type: 'boolean', default: false },
      { displayName: 'Disable Duet', name: 'disableDuet', type: 'boolean', default: false },
      { displayName: 'Disable Stitch', name: 'disableStitch', type: 'boolean', default: false },
      { displayName: 'Cover Timestamp (ms)', name: 'coverMs', type: 'number', default: 1000 },
      { displayName: 'Wait for Processing', name: 'waitForStatus', type: 'boolean', default: true, description: 'Poll publish status until TikTok finishes (up to ~3 min)' },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const out: INodeExecutionData[] = [];

    for (let i = 0; i < items.length; i++) {
      const accessToken = this.getNodeParameter('accessToken', i) as string;
      const source = this.getNodeParameter('source', i) as 'FILE_UPLOAD' | 'PULL_FROM_URL';
      const caption = (this.getNodeParameter('caption', i, '') as string).slice(0, 2200);
      const headers = { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json; charset=UTF-8' };

      const postInfo = {
        title: caption,
        privacy_level: this.getNodeParameter('privacy', i) as string,
        disable_comment: this.getNodeParameter('disableComment', i) as boolean,
        disable_duet: this.getNodeParameter('disableDuet', i) as boolean,
        disable_stitch: this.getNodeParameter('disableStitch', i) as boolean,
        video_cover_timestamp_ms: this.getNodeParameter('coverMs', i) as number,
      };

      let body: Record<string, unknown>;
      let videoBuffer: Buffer | undefined;

      if (source === 'PULL_FROM_URL') {
        const videoUrl = this.getNodeParameter('videoUrl', i) as string;
        body = { post_info: postInfo, source_info: { source: 'PULL_FROM_URL', video_url: videoUrl } };
      } else {
        const prop = this.getNodeParameter('binaryProperty', i) as string;
        videoBuffer = await this.helpers.getBinaryDataBuffer(i, prop);
        const size = videoBuffer.length;
        if (size > 64 * 1024 * 1024) {
          throw new Error(`Video is ${(size / 1048576).toFixed(1)} MB; single-chunk upload supports up to 64 MB. Re-encode smaller or use PULL_FROM_URL.`);
        }
        body = {
          post_info: postInfo,
          source_info: { source: 'FILE_UPLOAD', video_size: size, chunk_size: size, total_chunk_count: 1 },
        };
      }

      // 1) init
      const init = await axios.post(`${API}/post/publish/video/init/`, body, { headers, validateStatus: () => true });
      if (init.status >= 400 || init.data?.error?.code !== 'ok') {
        throw new Error(`TikTok init error ${init.status}: ${JSON.stringify(init.data)}`);
      }
      const publishId: string = init.data.data.publish_id;

      // 2) upload (binary mode)
      if (videoBuffer) {
        const uploadUrl: string = init.data.data.upload_url;
        const size = videoBuffer.length;
        const up = await axios.put(uploadUrl, videoBuffer, {
          headers: {
            'Content-Type': 'video/mp4',
            'Content-Length': String(size),
            'Content-Range': `bytes 0-${size - 1}/${size}`,
          },
          maxBodyLength: Infinity,
          validateStatus: () => true,
        });
        if (up.status >= 400) {
          throw new Error(`TikTok upload error ${up.status}: ${typeof up.data === 'string' ? up.data.slice(0, 500) : JSON.stringify(up.data)}`);
        }
      }

      // 3) status
      let status: Record<string, unknown> = {};
      if (this.getNodeParameter('waitForStatus', i) as boolean) {
        const deadline = Date.now() + 180_000;
        while (Date.now() < deadline) {
          const st = await axios.post(`${API}/post/publish/status/fetch/`, { publish_id: publishId }, { headers, validateStatus: () => true });
          status = st.data?.data ?? st.data;
          const s = (status as { status?: string }).status;
          if (s === 'PUBLISH_COMPLETE' || s === 'FAILED') break;
          await new Promise((r) => setTimeout(r, 4000));
        }
        if ((status as { status?: string }).status === 'FAILED') {
          throw new Error(`TikTok publish failed: ${JSON.stringify(status)}`);
        }
      }

      out.push({ json: { publishId, source, status } });
    }
    return [out];
  }
}
