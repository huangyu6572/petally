// pages/anti-fake/history/index.js
const { antiFakeApi } = require('../../../services/api');

Page({
  data: {
    list: [],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false,
    loadingMore: false,
  },

  onLoad() {
    this.loadData();
  },

  loadData() {
    this.setData({ loading: true });
    antiFakeApi.getHistory(1, this.data.pageSize)
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
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  loadMore() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    const nextPage = this.data.page + 1;
    antiFakeApi.getHistory(nextPage, this.data.pageSize)
      .then(res => {
        if (res && res.data) {
          const { items, total } = res.data;
          const newList = [...this.data.list, ...items];
          this.setData({
            list: newList,
            page: nextPage,
            hasMore: newList.length < total,
            loadingMore: false,
          });
        }
      })
      .catch(() => {
        this.setData({ loadingMore: false });
      });
  },

  goToResult(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/anti-fake/result/index?analysis_id=${id}` });
  },

  goToScan() {
    wx.navigateBack();
  },

  onPullDownRefresh() {
    this.setData({ list: [], page: 1, hasMore: true });
    this.loadData();
    wx.stopPullDownRefresh();
  },
});
