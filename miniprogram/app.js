/**
 * Petal 微信小程序 — 应用入口
 */
const { authApi } = require('./services/api');

App({
  globalData: {
    userInfo: null,
    isLoggedIn: false,
    loginCallbacks: [],   // 登录成功后的回调队列
  },

  onLaunch() {
    this.autoLogin();
  },

  /**
   * 自动登录：wx.login → 后端换 Token
   * 若本地已有 token 则静默续期，否则重新登录
   */
  autoLogin() {
    const token = wx.getStorageSync('access_token');
    if (token) {
      // 有 token 先标记为已登录，后台静默刷新
      this.globalData.isLoggedIn = true;
      this._silentRefresh();
      return;
    }
    this._doWechatLogin();
  },

  _doWechatLogin() {
    wx.login({
      success: (res) => {
        if (!res.code) return;
        authApi.wechatLogin(res.code).then((response) => {
          if (response.code === 0) {
            wx.setStorageSync('access_token', response.data.access_token);
            wx.setStorageSync('refresh_token', response.data.refresh_token);
            this.globalData.isLoggedIn = true;
            // 通知所有等待登录的回调
            this.globalData.loginCallbacks.forEach(cb => cb());
            this.globalData.loginCallbacks = [];
          }
        }).catch((err) => {
          console.error('Login failed:', err);
        });
      },
    });
  },

  _silentRefresh() {
    const refresh = wx.getStorageSync('refresh_token');
    if (!refresh) return;
    authApi.refreshToken(refresh).then((response) => {
      if (response && response.code === 0) {
        wx.setStorageSync('access_token', response.data.access_token);
        wx.setStorageSync('refresh_token', response.data.refresh_token);
      }
    }).catch(() => {
      // 刷新失败则重新登录
      this._doWechatLogin();
    });
  },

  /** 供页面调用：确保登录后执行 cb */
  requireLogin(cb) {
    if (this.globalData.isLoggedIn) {
      cb();
    } else {
      this.globalData.loginCallbacks.push(cb);
      this._doWechatLogin();
    }
  },
});
