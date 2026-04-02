// pages/promotion/list/index.js
const { promotionApi } = require('../../../services/api');

Page({
  data: {
    list: [],
    categories: ['宠物食品', '护肤用品', '玩具', '医疗保健', '清洁用品'],
    category: '',
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false,
    loadingMore: false,
  },

  onLoad() {
    this.loadData();
  },

  setCategory(e) {
    const cat = e.currentTarget.dataset.cat;
    if (cat === this.data.category) return;
    this.setData({ category: cat, list: [], page: 1, hasMore: true });
    this.loadData();
  },

  loadData() {
    this.setData({ loading: true });
    promotionApi.getList(1, this.data.pageSize, this.data.category || undefined)
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

  loadMore() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    const nextPage = this.data.page + 1;
    promotionApi.getList(nextPage, this.data.pageSize, this.data.category || undefined)
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

  goToDetail(e) {
    const id = e.currentTarget.dataset.id;
    promotionApi.track(id, 'view', 'list').catch(() => {});
    wx.navigateTo({ url: `/pages/promotion/detail/index?id=${id}` });
  },

  onPullDownRefresh() {
    this.setData({ list: [], page: 1, hasMore: true });
    this.loadData();
    wx.stopPullDownRefresh();
  },

  onReachBottom() {
    this.loadMore();
  },
});
