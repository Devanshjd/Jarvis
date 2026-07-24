export function floatTo16BitPCM(float32Array: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32Array.length * 2)
  const view = new DataView(buffer)
  let offset = 0
  for (let i = 0; i < float32Array.length; i += 1, offset += 2) {
    const sample = Math.max(-1, Math.min(1, float32Array[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return buffer
}

export function base64ToFloat32(base64String: string): Float32Array {
  const binaryString = atob(base64String)
  const bytes = new Uint8Array(binaryString.length)
  for (let i = 0; i < binaryString.length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  const int16Array = new Int16Array(bytes.buffer)
  const float32Array = new Float32Array(int16Array.length)
  for (let i = 0; i < int16Array.length; i += 1) {
    float32Array[i] = int16Array[i] / 32768.0
  }
  return float32Array
}

export function downsampleTo16000(float32Array: Float32Array, inputSampleRate: number): Float32Array {
  if (inputSampleRate === 16000) return float32Array

  const compression = inputSampleRate / 16000
  const length = Math.max(1, Math.floor(float32Array.length / compression))
  const result = new Float32Array(length)

  let index = 0
  let inputIndex = 0

  while (index < length) {
    result[index] = float32Array[Math.floor(inputIndex)] ?? 0
    inputIndex += compression
    index += 1
  }
  return result
}

/** Encode 16-bit PCM (16kHz mono) as a base64 WAV — what the local /api/voice/local
 *  endpoint (Whisper) expects. */
export function encodeWavBase64(float32: Float32Array, sampleRate = 16000): string {
  const pcm = floatTo16BitPCM(float32) // ArrayBuffer of Int16 LE
  const dataLen = pcm.byteLength
  const buffer = new ArrayBuffer(44 + dataLen)
  const view = new DataView(buffer)
  const w = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }
  w(0, 'RIFF')
  view.setUint32(4, 36 + dataLen, true)
  w(8, 'WAVE')
  w(12, 'fmt ')
  view.setUint32(16, 16, true) // PCM chunk size
  view.setUint16(20, 1, true) // PCM format
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  w(36, 'data')
  view.setUint32(40, dataLen, true)
  new Uint8Array(buffer, 44).set(new Uint8Array(pcm))
  // base64 without spread (large arrays)
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

/** Convert a recorded audio Blob (webm/opus from MediaRecorder) to a base64 WAV
 *  at 16kHz mono, ready for local Whisper. */
export async function blobToWavBase64(blob: Blob): Promise<string> {
  const arrayBuf = await blob.arrayBuffer()
  const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new AC()
  try {
    const audioBuf = await ctx.decodeAudioData(arrayBuf)
    const mono = audioBuf.getChannelData(0)
    const ds = downsampleTo16000(mono, audioBuf.sampleRate)
    return encodeWavBase64(ds, 16000)
  } finally {
    void ctx.close()
  }
}
