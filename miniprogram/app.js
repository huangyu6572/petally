/**
 * Petal 微信小程序 — 应用入口
 */
const { authApi } = require('./services/api');

App({
  globalData: {
    userInfo: null,
    isLoggedIn: false,
  },

  onLaunch() {
    this.autoLogin();
  },

  /** 自动登录：wx.login → 后端换 Token */
  autoLogin() {
    wx.login({
      success: (res) => {
        if (res.code) {
          authApi.wechatLogin(res.code).then((response) => {
            if (response.code === 0) {
              wx.setStorageSync('access_token', response.data.access_token);
              wx.setStorageSync('refresh_token', response.data.refresh_token);
              this.globalData.isLoggedIn = true;
            }
          }).catch((err) => {
            console.error('Auto login failed:', err);
          });
        }
      },
    });
  },
});
