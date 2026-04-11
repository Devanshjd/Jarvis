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
