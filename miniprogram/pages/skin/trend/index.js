// pages/skin/trend/index.js
const { skinApi } = require('../../../services/api');

Page({
  data: {
    days: 30,
    loading: false,
    trendData: [],
    stats: {},
  },

  onLoad() {
    this.loadTrend();
  },

  setRange(e) {
    const days = e.currentTarget.dataset.days;
    this.setData({ days });
    this.loadTrend();
  },

  loadTrend() {
    this.setData({ loading: true, trendData: [] });
    skinApi.getTrend(this.data.days)
      .then(res => {
        if (res && res.data && res.data.data) {
          const raw = res.data.data;
          const trendData = raw.map(item => ({
            ...item,
            short_date: item.date ? item.date.slice(5) : '',
          }));
          // 计算统计信息
          const scores = trendData.map(d => d.overall_score).filter(Boolean);
          const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
          const trend = scores.length >= 2 ? scores[scores.length - 1] - scores[0] : 0;
          this.setData({
            trendData,
            stats: { avg_score: avg, trend, total: trendData.length },
            loading: false,
          });
        } else {
          this.setData({ loading: false });
        }
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },
});
