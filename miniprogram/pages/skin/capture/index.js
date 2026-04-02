// pages/skin/capture/index.js
const { skinApi } = require('../../../services/api');

Page({
  data: {
    imagePath: '',
    analysisType: 'general',
    uploading: false,
    analysisTypes: [
      { label: '综合分析', value: 'general' },
      { label: '皮肤病', value: 'dermatology' },
      { label: '过敏反应', value: 'allergy' },
      { label: '毛发状况', value: 'hair' },
    ],
  },

  onLoad() {
    const app = getApp();
    app.requireLogin(() => {});
  },

  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: (res) => {
        const filePath = res.tempFiles[0].tempFilePath;
        this.setData({ imagePath: filePath });
      },
    });
  },

  selectType(e) {
    this.setData({ analysisType: e.currentTarget.dataset.value });
  },

  startAnalysis() {
    if (!this.data.imagePath || this.data.uploading) return;
    const app = getApp();
    app.requireLogin(() => {
      this.setData({ uploading: true });
      wx.showLoading({ title: '上传中...', mask: true });

      skinApi.submitAnalysis(this.data.imagePath, this.data.analysisType)
        .then(res => {
          wx.hideLoading();
          if (res && res.data && res.data.id) {
            wx.navigateTo({
              url: `/pages/skin/analyzing/index?analysis_id=${res.data.id}`,
            });
          }
        })
        .catch(err => {
          wx.hideLoading();
          const msg = (err && err.message) || '上传失败，请重试';
          wx.showToast({ title: msg, icon: 'none', duration: 2500 });
        })
        .finally(() => {
          this.setData({ uploading: false });
        });
    });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/skin/history/index' });
  },
});
