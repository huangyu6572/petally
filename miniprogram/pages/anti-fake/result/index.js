// pages/anti-fake/result/index.js
const { antiFakeApi } = require('../../../services/api');

Page({
  data: {
    loading: true,
    result: null,
    error: null,
  },

  onLoad(options) {
    const { analysis_id } = options;
    if (!analysis_id) {
      this.setData({ loading: false, error: '无效的查询结果' });
      return;
    }
    antiFakeApi.getResult(analysis_id)
      .then(res => {
        if (res && res.data) {
          this.setData({ loading: false, result: res.data });
        } else {
          this.setData({ loading: false, error: '未获取到结果' });
        }
      })
      .catch(err => {
        const msg = (err && err.message) || '加载失败，请重试';
        this.setData({ loading: false, error: msg });
      });
  },

  scanAgain() {
    wx.navigateBack({ delta: 1 });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/anti-fake/history/index' });
  },
});
