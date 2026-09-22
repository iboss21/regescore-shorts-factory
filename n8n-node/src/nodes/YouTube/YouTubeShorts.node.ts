
import type { IExecuteFunctions, INodeType, INodeTypeDescription } from 'n8n-workflow';
export class YouTubeShorts implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'YouTube Shorts (Stub)',
    name: 'youTubeShorts',
    icon: 'fa:youtube',
    group: ['output'],
    version: 1,
    description: 'Resumable upload to YouTube (init + PUT). Fill OAuth + calls.',
    defaults: { name: 'YouTube Shorts (Stub)' },
    inputs: ['main'],
    outputs: ['main'],
    properties: [
      { displayName: 'Title', name: 'title', type: 'string', default: '' },
      { displayName: 'Description', name: 'description', type: 'string', typeOptions: { rows: 4 }, default: '' },
      { displayName: 'Video Binary Property', name: 'binaryProperty', type: 'string', default: 'data' }
    ],
  };
  async execute(this: IExecuteFunctions) { return [this.getInputData()]; }
}
