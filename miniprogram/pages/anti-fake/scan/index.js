// pages/anti-fake/scan/index.js
const { antiFakeApi } = require('../../../services/api');

Page({
  data: {
    scanning: false,
  },

  onLoad() {
    const app = getApp();
    app.requireLogin(() => {});
  },

  handleScan() {
    if (this.data.scanning) return;
    const app = getApp();
    app.requireLogin(() => {
      this.setData({ scanning: true });
      wx.scanCode({
        onlyFromCamera: false,
        success: (res) => {
          const code = res.result;
          this._verifyCode(code);
        },
        fail: () => {
          this.setData({ scanning: false });
        },
      });
    });
  },

  _verifyCode(code) {
    wx.showLoading({ title: '验证中...', mask: true });
    antiFakeApi.verify(code)
      .then(res => {
        wx.hideLoading();
        if (res && res.data) {
          wx.navigateTo({
            url: `/pages/anti-fake/result/index?analysis_id=${res.data.id}&code=${encodeURIComponent(code)}`,
          });
        }
      })
      .catch(err => {
        wx.hideLoading();
        const msg = (err && err.message) || '验证失败，请重试';
        wx.showToast({ title: msg, icon: 'none', duration: 2500 });
      })
      .finally(() => {
        this.setData({ scanning: false });
      });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/anti-fake/history/index' });
  },
});
