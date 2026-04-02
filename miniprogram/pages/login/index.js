// pages/login/index.js
Page({
  data: {
    loading: false,
  },

  handleLogin() {
    if (this.data.loading) return;
    this.setData({ loading: true });

    const app = getApp();
    app._doWechatLogin()
      .then(() => {
        // 登录成功，返回上一页或首页
        const pages = getCurrentPages();
        if (pages.length > 1) {
          wx.navigateBack();
        } else {
          wx.switchTab({ url: '/pages/index/index' });
        }
      })
      .catch(err => {
        console.error('登录失败', err);
        wx.showToast({ title: '登录失败，请重试', icon: 'none' });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },
});
