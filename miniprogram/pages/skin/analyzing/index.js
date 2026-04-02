// pages/skin/analyzing/index.js
const { skinApi } = require('../../../services/api');

const HINTS = [
  '正在识别图像特征...',
  '深度学习模型分析中...',
  '对比专业肌肤数据库...',
  '生成个性化报告...',
  '即将完成...',
];

Page({
  data: {
    progress: 0,
    hint: HINTS[0],
    failed: false,
  },

  onLoad(options) {
    this.analysisId = options.analysis_id;
    this.pollCount = 0;
    this.maxPoll = 40;
    this.progressTimer = null;
    this.pollTimer = null;
    this._startProgressAnim();
    this._poll();
  },

  onUnload() {
    this._clearTimers();
  },

  _clearTimers() {
    if (this.progressTimer) clearInterval(this.progressTimer);
    if (this.pollTimer) clearTimeout(this.pollTimer);
  },

  _startProgressAnim() {
    let p = 0;
    this.progressTimer = setInterval(() => {
      if (p < 90) {
        p = Math.min(p + 1, 90);
        const hintIdx = Math.floor((p / 90) * (HINTS.length - 1));
        this.setData({ progress: p, hint: HINTS[hintIdx] });
      }
    }, 300);
  },

  _poll() {
    if (this.pollCount >= this.maxPoll) {
      this._clearTimers();
      this.setData({ failed: true });
      return;
    }
    this.pollCount++;
    skinApi.getResult(this.analysisId)
      .then(res => {
        const status = res && res.data && res.data.status;
        if (status === 'completed') {
          this._clearTimers();
          this.setData({ progress: 100, hint: '分析完成！' });
          setTimeout(() => {
            wx.redirectTo({
              url: `/pages/skin/result/index?analysis_id=${this.analysisId}`,
            });
          }, 600);
        } else if (status === 'failed') {
          this._clearTimers();
          this.setData({ failed: true });
        } else {
          this.pollTimer = setTimeout(() => this._poll(), 2000);
        }
      })
      .catch(() => {
        this.pollTimer = setTimeout(() => this._poll(), 3000);
      });
  },

  goBack() {
    wx.navigateBack({ delta: 2 });
  },
});
