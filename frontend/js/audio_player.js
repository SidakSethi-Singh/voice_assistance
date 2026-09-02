/**
 * Low-latency progressive streaming audio player using Web Audio API.
 * Supports continuous chunk queuing, scheduled sequential playback,
 * and instant flushing/cancellation for barge-in interruptions.
 */
class StreamingAudioPlayer {
  constructor(onPlaybackStart, onPlaybackEnd) {
    this.onPlaybackStart = onPlaybackStart;
    this.onPlaybackEnd = onPlaybackEnd;
    this.audioContext = null;
    this.isPlaying = false;
    this.activeSources = [];
    this.audioQueue = [];
    this.isProcessingQueue = false;
    this.nextScheduledTime = 0;
  }

  _ensureAudioContext() {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }
  }

  async queueAudioChunk(arrayBuffer) {
    this._ensureAudioContext();

    this.audioQueue.push(arrayBuffer);
    if (!this.isProcessingQueue) {
      this._processQueue();
    }
  }

  async _processQueue() {
    if (this.audioQueue.length === 0) {
      this.isProcessingQueue = false;
      return;
    }

    this.isProcessingQueue = true;
    const chunk = this.audioQueue.shift();

    try {
      // Decode audio data chunk
      const audioBuffer = await this.audioContext.decodeAudioData(chunk.slice(0));
      this._scheduleBuffer(audioBuffer);
    } catch (err) {
      // Small chunks or header splits may fail standalone decode; can safely ignore if partial
      console.debug("Audio chunk decode frame pass:", err);
    }

    // Process next chunk in queue
    setTimeout(() => this._processQueue(), 10);
  }

  _scheduleBuffer(audioBuffer) {
    if (!this.audioContext) return;

    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);

    const currentTime = this.audioContext.currentTime;
    // Schedule seamlessly at the end of the previous buffer
    if (this.nextScheduledTime < currentTime) {
      this.nextScheduledTime = currentTime + 0.02; // Small initial buffer
    }

    source.start(this.nextScheduledTime);
    this.nextScheduledTime += audioBuffer.duration;
    this.activeSources.push(source);

    if (!this.isPlaying) {
      this.isPlaying = true;
      if (this.onPlaybackStart) this.onPlaybackStart();
    }

    source.onended = () => {
      const idx = this.activeSources.indexOf(source);
      if (idx !== -1) {
        this.activeSources.splice(idx, 1);
      }

      if (this.activeSources.length === 0 && this.audioQueue.length === 0) {
        this.isPlaying = false;
        if (this.onPlaybackEnd) this.onPlaybackEnd();
      }
    };
  }

  /**
   * Barge-in interruption handler:
   * Immediately stops all currently playing audio source nodes,
   * empties the audio queue, and resets scheduling times.
   */
  flush() {
    console.log("Flushing streaming audio player (Barge-in / Interruption).");
    
    // Stop and disconnect all active sources immediately
    for (const source of this.activeSources) {
      try {
        source.stop(0);
        source.disconnect();
      } catch (e) {}
    }
    this.activeSources = [];
    this.audioQueue = [];
    this.nextScheduledTime = 0;
    this.isProcessingQueue = false;

    if (this.isPlaying) {
      this.isPlaying = false;
      if (this.onPlaybackEnd) this.onPlaybackEnd();
    }
  }
}

window.StreamingAudioPlayer = StreamingAudioPlayer;
