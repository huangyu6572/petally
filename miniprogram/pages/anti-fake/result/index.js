// pages/anti-fake/result/index.js
// v2: 支持条形码查询结果 + 品牌跳转结果两种展示

Page({
  data: {
    type: '',        // "barcode" or "brand"
    product: null,   // 条形码查询到的产品信息
    brand: null,     // 品牌跳转信息
    error: null,
  },

  onLoad(options) {
    const { type, data } = options;
    if (!type || !data) {
      this.setData({ error: '无效的查询结果' });
      return;
    }
    try {
      const parsed = JSON.parse(decodeURIComponent(data));
      if (type === 'barcode') {
        this.setData({ type: 'barcode', product: parsed });
      } else if (type === 'brand') {
        this.setData({ type: 'brand', brand: parsed });
      }
    } catch (e) {
      this.setData({ error: '数据解析失败' });
    }
  },

  /** 品牌跳转 —— 打开官方验证 URL */
  openVerifyUrl() {
    const brand = this.data.brand;
    if (!brand || !brand.verify_url) return;

    if (brand.verify_type === 'miniprogram' && brand.miniprogram_id) {
      // 跳转到品牌小程序
      wx.navigateToMiniProgram({
        appId: brand.miniprogram_id,
        path: brand.miniprogram_path || '',
        fail: () => {
          // 跳转小程序失败，fallback 到复制链接
          if (brand.verify_url) {
            wx.setClipboardData({
              data: brand.verify_url,
              success: () => {
                wx.showToast({ title: '链接已复制，请在浏览器中打开', icon: 'none' });
              },
            });
          }
        },
      });
    } else if (brand.verify_url) {
      // web-view 打开或复制链接
      wx.setClipboardData({
        data: brand.verify_url,
        success: () => {
          wx.showToast({ title: '官方验证链接已复制到剪贴板', icon: 'none', duration: 2500 });
        },
      });
    }
  },

  /** 查看 Open Beauty Facts 原始页面 */
  openSourceUrl() {
    const p = this.data.product;
    if (p && p.source_url) {
      wx.setClipboardData({
        data: p.source_url,
        success: () => {
          wx.showToast({ title: '链接已复制，可在浏览器中查看详情', icon: 'none', duration: 2500 });
        },
      });
    }
  },

  scanAgain() {
    wx.navigateBack({ delta: 1 });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/anti-fake/history/index' });
  },
});
