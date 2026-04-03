// pages/anti-fake/scan/index.js
// v2: 条形码查询 + 品牌防伪跳转
const { antiFakeApi } = require('../../../services/api');

Page({
  data: {
    scanning: false,
    showBrandSelect: false,
    brands: [],
    searchBrand: '',
    filteredBrands: [],
  },

  onLoad() {
    const app = getApp();
    app.requireLogin(() => {});
    this._loadBrands();
  },

  /** 加载支持的品牌列表 */
  _loadBrands() {
    antiFakeApi.getBrands().then(res => {
      if (res && res.data) {
        const brands = res.data.brands || [];
        this.setData({ brands, filteredBrands: brands });
      }
    }).catch(() => {});
  },

  /** 扫描条形码 —— 查询产品备案信息 */
  handleScanBarcode() {
    if (this.data.scanning) return;
    const app = getApp();
    app.requireLogin(() => {
      this.setData({ scanning: true });
      wx.scanCode({
        onlyFromCamera: false,
        scanType: ['barCode'],
        success: (res) => {
          this._lookupBarcode(res.result);
        },
        fail: () => {
          this.setData({ scanning: false });
        },
      });
    });
  },

  /** 条形码查询 */
  _lookupBarcode(barcode) {
    wx.showLoading({ title: '查询中...', mask: true });
    antiFakeApi.lookupBarcode(barcode)
      .then(res => {
        wx.hideLoading();
        if (res && res.data && res.data.found) {
          wx.navigateTo({
            url: `/pages/anti-fake/result/index?type=barcode&data=${encodeURIComponent(JSON.stringify(res.data.product))}`,
          });
        } else {
          const msg = (res && res.data && res.data.message) || '该条形码暂未被收录';
          wx.showModal({
            title: '未找到产品',
            content: msg + '\n\n是否尝试品牌官方防伪验证？',
            confirmText: '选择品牌',
            cancelText: '返回',
            success: (modalRes) => {
              if (modalRes.confirm) {
                this.setData({ showBrandSelect: true });
              }
            },
          });
        }
      })
      .catch(err => {
        wx.hideLoading();
        const msg = (err && err.message) || '查询失败，请重试';
        wx.showToast({ title: msg, icon: 'none', duration: 2500 });
      })
      .finally(() => {
        this.setData({ scanning: false });
      });
  },

  /** 打开品牌选择列表 */
  handleBrandVerify() {
    this.setData({ showBrandSelect: true });
  },

  /** 品牌搜索 */
  onBrandSearch(e) {
    const keyword = (e.detail.value || '').toLowerCase().trim();
    this.setData({ searchBrand: keyword });
    if (!keyword) {
      this.setData({ filteredBrands: this.data.brands });
      return;
    }
    const filtered = this.data.brands.filter(b =>
      b.brand_name.toLowerCase().includes(keyword) ||
      b.brand_name_en.toLowerCase().includes(keyword)
    );
    this.setData({ filteredBrands: filtered });
  },

  /** 选择品牌 → 跳转官方验证 */
  onSelectBrand(e) {
    const brand = e.currentTarget.dataset.brand;
    this.setData({ showBrandSelect: false });
    wx.showLoading({ title: '获取验证地址...' });
    antiFakeApi.brandVerify(brand.brand_name)
      .then(res => {
        wx.hideLoading();
        if (res && res.data && res.data.found) {
          wx.navigateTo({
            url: `/pages/anti-fake/result/index?type=brand&data=${encodeURIComponent(JSON.stringify(res.data.brand))}`,
          });
        } else {
          wx.showToast({
            title: `暂不支持${brand.brand_name}的跳转`,
            icon: 'none',
          });
        }
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: '获取失败，请重试', icon: 'none' });
      });
  },

  /** 关闭品牌选择 */
  closeBrandSelect() {
    this.setData({ showBrandSelect: false, searchBrand: '', filteredBrands: this.data.brands });
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/anti-fake/history/index' });
  },
});
