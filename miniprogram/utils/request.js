/**
 * Petal 微信小程序 — API 请求封装
 * 前后端解耦：所有后端通信通过此模块
 */

const BASE_URL = 'https://api.petal.example.com/api/v1';

/**
 * 通用请求方法
 */
const request = (url, method, data, options = {}) => {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('access_token');
    wx.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options.header,
      },
      timeout: options.timeout || 30000,
      success(res) {
        if (res.statusCode === 401) {
          // Token 过期，尝试刷新
          refreshToken().then(() => {
            // 重试原请求
            request(url, method, data, options).then(resolve).catch(reject);
          }).catch(() => {
            // 刷新失败，跳转登录
            wx.navigateTo({ url: '/pages/login/index' });
            reject(new Error('Authentication required'));
          });
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res.data);
        }
      },
      fail(err) {
        reject(err);
      },
    });
  });
};

const get = (url, params) => request(url, 'GET', params);
const post = (url, data) => request(url, 'POST', data);

/**
 * 刷新 Token
 */
const refreshToken = () => {
  const refresh = wx.getStorageSync('refresh_token');
  return post('/auth/refresh', { refresh_token: refresh }).then(res => {
    wx.setStorageSync('access_token', res.data.access_token);
    wx.setStorageSync('refresh_token', res.data.refresh_token);
  });
};

module.exports = { get, post, request, BASE_URL };
