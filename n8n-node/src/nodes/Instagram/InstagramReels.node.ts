
import type { IExecuteFunctions, INodeExecutionData, INodeType, INodeTypeDescription } from 'n8n-workflow';
import axios from 'axios';

export class InstagramReels implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'Instagram Reels Publisher',
    name: 'instagramReelsPublisher',
    icon: 'file:instagram.svg',
    group: ['output'],
    version: 1,
    description: 'Publish a video to Instagram Reels via the Graph API',
    defaults: { name: 'Instagram Reels Publisher' },
    inputs: ['main'],
    outputs: ['main'],
    properties: [
      { displayName: 'IG Business User ID', name: 'igUserId', type: 'string', default: '', required: true, description: 'Numeric account ID (not @username)' },
      { displayName: 'Video URL', name: 'videoUrl', type: 'string', default: '', required: true, description: 'Public MP4 URL (S3 presigned recommended)' },
      { displayName: 'Caption', name: 'caption', type: 'string', typeOptions: { rows: 5 }, default: '' },
      { displayName: 'Share to Feed', name: 'shareToFeed', type: 'boolean', default: true },
      { displayName: 'Access Token', name: 'accessToken', type: 'string', typeOptions: { password: true }, default: '', required: true, description: 'with instagram_content_publish scope' },
      { displayName: 'Graph API Version', name: 'graphVersion', type: 'string', default: 'v19.0' }
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const out: INodeExecutionData[] = [];

    for (let i = 0; i < items.length; i++) {
      const igUserId = this.getNodeParameter('igUserId', i) as string;
      const videoUrl = this.getNodeParameter('videoUrl', i) as string;
      const caption = this.getNodeParameter('caption', i, '') as string;
      const shareToFeed = this.getNodeParameter('shareToFeed', i) as boolean;
      const accessToken = this.getNodeParameter('accessToken', i) as string;
      const graphVersion = this.getNodeParameter('graphVersion', i) as string;
      const base = `https://graph.facebook.com/${graphVersion}`;

      const containerRes = await axios.post(`${base}/${igUserId}/media`, null, {
        params: { media_type: 'REELS', video_url: videoUrl, caption, share_to_feed: shareToFeed ? 'true' : 'false', access_token: accessToken },
        validateStatus: () => true,
      });
      if (containerRes.status >= 400) {
        throw new Error(`IG container error ${containerRes.status}: ${JSON.stringify(containerRes.data)}`);
      }
      const creationId = containerRes.data.id;

      const publishRes = await axios.post(`${base}/${igUserId}/media_publish`, null, {
        params: { creation_id: creationId, access_token: accessToken },
        validateStatus: () => true,
      });
      if (publishRes.status >= 400) {
        throw new Error(`IG publish error ${publishRes.status}: ${JSON.stringify(publishRes.data)}`);
      }

      out.push({ json: { creationId, publish: publishRes.data } });
    }
    return [out];
  }
}
