// pages/skin/history/index.js
const { skinApi } = require('../../../services/api');

Page({
  data: {
    activeTab: 'list',
    list: [],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false,
  },

  onLoad() {
    this.loadData();
  },

  switchTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },

  loadData() {
    this.setData({ loading: true });
    skinApi.getHistory(1, this.data.pageSize)
      .then(res => {
        if (res && res.data) {
          const { items, total } = res.data;
          this.setData({
            list: items,
            page: 1,
            hasMore: items.length < total,
            loading: false,
          });
        }
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  goToResult(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/skin/result/index?analysis_id=${id}` });
  },

  onPullDownRefresh() {
    this.setData({ list: [], page: 1, hasMore: true });
    this.loadData();
    wx.stopPullDownRefresh();
  },
});
