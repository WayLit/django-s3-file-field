import axios from 'axios';

// Description of a part from initializeUpload()
interface PartInfo {
  part_number: number;
  size: number;
  upload_url: string;
}
// Description of the upload from initializeUpload()
interface MultipartInfo {
  upload_signature: string;
  object_key: string;
  upload_id: string;
  parts: PartInfo[];
}
// Description of a part which has been uploaded by uploadPart()
interface UploadedPart {
  part_number: number;
  size: number;
  etag: string;
}
// Return value from uploadFile()
export interface UploadResult {
  value: string;
  state: 'aborted' | 'successful' | 'error';
}

export interface ProgressEvent {
  loaded?: number;
  total?: number;
  state: 'initializing' | 'sending' | 'finalizing';
}

type ProgressCallback = (progress: ProgressEvent) => void;

export default class S3FFClient {
  constructor(
    protected readonly baseUrl: string,
    private readonly onProgress: ProgressCallback = () => { /* no-op*/ },
  ) {
    // Strip any trailing slash
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Initializes an upload.
   *
   * @param file The file to upload.
   * @param fieldId The Django field identifier.
   */
  protected async initializeUpload(file: File, fieldId: string): Promise<MultipartInfo> {
    this.onProgress({ state: 'initializing' });
    const response = await axios.post(`${this.baseUrl}/upload-initialize/`, { 'field_id': fieldId, 'file_name': file.name, 'file_size': file.size });
    return response.data;
  }

  /**
   * Uploads all the parts in a file directly to an object store in serial.
   *
   * @param file The file to upload.
   * @param parts The list of parts describing how to break up the file.
   */
  protected async uploadParts(file: File, parts: PartInfo[]): Promise<UploadedPart[]> {
    const uploadedParts: UploadedPart[] = [];
    let index = 0;
    for (const part of parts) {
      const chunk = file.slice(index, index + part.size);
      const response = await axios.put(part.upload_url, chunk, {
        onUploadProgress: (e) => {
          this.onProgress({
            loaded: index + e.loaded,
            total: file.size,
            state: 'sending',
          });
        },
      });

      uploadedParts.push({
        part_number: part.part_number,
        size: part.size,
        etag: response.headers.etag
      });
      index += part.size;
    }
    return uploadedParts;
  }

  /**
   * Completes an upload.
   *
   * The object will exist in the object store after completion.
   *
   * @param multipartInfo The information describing the multipart upload.
   * @param parts The parts that were uploaded.
   */
  protected async completeUpload(multipartInfo: MultipartInfo, parts: UploadedPart[]): Promise<void> {
    const response = await axios.post(`${this.baseUrl}/upload-complete/`, {
      upload_signature: multipartInfo.upload_signature,
      upload_id: multipartInfo.upload_id,
      parts: parts,
    });
    const { complete_url, body } = response.data;

    // Send the CompleteMultipartUpload operation to S3
    await axios.post(complete_url, body, {
      headers: {
        // By default, Axios sets "Content-Type: application/x-www-form-urlencoded" on POST
        // requests. This causes AWS's API to interpret the request body as additional parameters
        // to include in the signature validation, causing it to fail.
        // So, do not send this request with any Content-Type, as that is what's specified by the
        // CompleteMultipartUpload docs.
        'Content-Type': null,
      },
    });
  }

  /**
   * Finalizes an upload.
   *
   * This will only succeed if the object is already present in the object store.
   *
   * @param multipartInfo Signed information returned from /upload-complete/.
   */
  protected async finalize(multipartInfo: MultipartInfo): Promise<string> {
    this.onProgress({ state: 'finalizing' });
    const response = await axios.post(`${this.baseUrl}/finalize/`, {
      upload_signature: multipartInfo.upload_signature,
    });
    const { field_value } = response.data;
    return field_value;
  }

  /**
   * Uploads a file using multipart upload.
   *
   * @param file The file to upload.
   * @param fieldId The Django field identifier.
   */
  public async uploadFile(file: File, fieldId: string): Promise<UploadResult> {
    const multipartInfo = await this.initializeUpload(file, fieldId);
    const parts = await this.uploadParts(file, multipartInfo.parts);
    await this.completeUpload(multipartInfo, parts);
    const field_value = await this.finalize(multipartInfo);
    return {
      value: field_value,
      state: 'successful',
    }
  }
}
