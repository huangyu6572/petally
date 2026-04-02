// pages/skin/result/index.js
const { skinApi, promotionApi } = require('../../../services/api');

Page({
  data: {
    loading: true,
    result: null,
    recommendations: [],
  },

  onLoad(options) {
    this.analysisId = options.analysis_id;
    this._loadResult();
  },

  _loadResult() {
    skinApi.getResult(this.analysisId)
      .then(res => {
        if (res && res.data) {
          this.setData({ loading: false, result: res.data });
          // 加载推荐产品
          return promotionApi.getRecommend(this.analysisId);
        }
      })
      .then(res => {
        if (res && res.data && res.data.items) {
          this.setData({ recommendations: res.data.items.slice(0, 3) });
        }
      })
      .catch(() => {
        this.setData({ loading: false });
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  goToPromoDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/promotion/detail/index?id=${id}` });
  },

  goCapture() {
    wx.navigateBack({ delta: 2 });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/skin/history/index' });
  },
});
