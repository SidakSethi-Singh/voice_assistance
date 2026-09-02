/**
 * Captures microphone audio using Web Audio API,
 * downsamples/resamples to 16kHz 16-bit linear PCM mono,
 * and passes raw byte buffers to the provided callback.
 */
class AudioRecorder {
  constructor(onAudioChunk, onAudioLevel) {
    this.onAudioChunk = onAudioChunk;
    this.onAudioLevel = onAudioLevel;
    this.audioContext = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.processorNode = null;
    this.analyser = null;
    this.isRecording = false;
  }

  async start() {
    if (this.isRecording) return;

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      });

      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      
      // Analyser for visualizer
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.sourceNode.connect(this.analyser);

      // ScriptProcessor for raw PCM chunking
      const bufferSize = 2048;
      this.processorNode = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

      this.processorNode.onaudioprocess = (e) => {
        if (!this.isRecording) return;

        const inputData = e.inputBuffer.getChannelData(0);
        
        // Convert Float32Array to 16-bit signed PCM ArrayBuffer
        const pcm16 = new Int16Array(inputData.length);
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          sum += Math.abs(s);
        }

        // Calculate RMS audio level (0 - 1)
        const rms = Math.sqrt(sum / inputData.length);
        if (this.onAudioLevel) {
          this.onAudioLevel(rms);
        }

        if (this.onAudioChunk) {
          this.onAudioChunk(pcm16.buffer);
        }
      };

      this.sourceNode.connect(this.processorNode);
      this.processorNode.connect(this.audioContext.destination);

      this.isRecording = true;
      return true;
    } catch (err) {
      console.error("Failed to start audio recording:", err);
      throw err;
    }
  }

  getFrequencyData(array) {
    if (this.analyser) {
      this.analyser.getByteFrequencyData(array);
    }
  }

  stop() {
    this.isRecording = false;

    if (this.processorNode && this.sourceNode) {
      this.sourceNode.disconnect(this.processorNode);
      this.processorNode.disconnect();
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}

window.AudioRecorder = AudioRecorder;
