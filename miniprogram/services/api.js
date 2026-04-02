/**
 * Petal 微信小程序 — 后端 API 服务层
 * 按模块组织所有 API 调用
 */

const { get, post, request, BASE_URL } = require('../utils/request');

// ========== 认证模块 ==========
const authApi = {
  /** 微信登录 */
  wechatLogin(code) {
    return post('/auth/wechat-login', { code });
  },
  /** 刷新 token */
  refreshToken(refreshToken) {
    return post('/auth/refresh', { refresh_token: refreshToken });
  },
};

// ========== 防伪查询模块 ==========
const antiFakeApi = {
  /** 查询防伪码 */
  verify(code) {
    return post('/anti-fake/verify', { code });
  },

  /** 获取单条查询结果 */
  getResult(analysisId) {
    return get(`/anti-fake/results/${analysisId}`);
  },

  /** 获取查询历史 */
  getHistory(page = 1, size = 20) {
    return get(`/anti-fake/history?page=${page}&size=${size}`);
  },
};

// ========== AI 肌肤分析模块 ==========
const skinApi = {
  /** 提交肌肤分析 (图片上传) */
  submitAnalysis(filePath, analysisType = 'face_full') {
    return new Promise((resolve, reject) => {
      const token = wx.getStorageSync('access_token');
      wx.uploadFile({
        url: `${BASE_URL}/skin/analyze`,
        filePath,
        name: 'image',
        formData: { analysis_type: analysisType },
        header: { 'Authorization': `Bearer ${token}` },
        success(res) {
          resolve(JSON.parse(res.data));
        },
        fail: reject,
      });
    });
  },

  /** 获取分析结果 (轮询) */
  getResult(analysisId) {
    return get(`/skin/analyze/${analysisId}`);
  },

  /** 获取分析历史 */
  getHistory(page = 1, size = 10) {
    return get(`/skin/history?page=${page}&size=${size}`);
  },

  /** 获取肌肤趋势 */
  getTrend(days = 90) {
    return get(`/skin/trend?days=${days}`);
  },
};

// ========== 商品推广模块 ==========
const promotionApi = {
  /** 获取推广列表 */
  getList(page = 1, size = 20, category = '') {
    let url = `/promotions?page=${page}&size=${size}`;
    if (category) url += `&category=${category}`;
    return get(url);
  },

  /** 获取推广详情 */
  getDetail(promotionId) {
    return get(`/promotions/${promotionId}`);
  },

  /** 领取优惠券 */
  claimCoupon(promotionId) {
    return post(`/promotions/${promotionId}/claim-coupon`);
  },

  /** 获取个性化推荐 */
  getRecommend(analysisId = '') {
    let url = '/promotions/recommend';
    if (analysisId) url += `?analysis_id=${analysisId}`;
    return get(url);
  },

  /** 记录推广行为 */
  track(promotionId, action, source) {
    return post(`/promotions/${promotionId}/track`, { action, source });
  },

  /** 生成分享信息 */
  share(promotionId) {
    return post(`/promotions/${promotionId}/share`);
  },
};

module.exports = { authApi, antiFakeApi, skinApi, promotionApi };
