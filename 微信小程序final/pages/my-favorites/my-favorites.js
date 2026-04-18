const app = getApp();

Page({
  data: {
    favorites: [],
    favoritesCount: 0,
  },

  onLoad() {
    this.loadFavorites();
  },

  onShow() {
    this.loadFavorites();
  },

  // 加载收藏列表
  loadFavorites() {
    const favorites = app.globalData.favorites || [];
    
    // 格式化时间
    const formattedFavorites = favorites.map(fav => {
      return {
        ...fav,
        favoritedTime: this.formatDate(fav.favoritedAt || Date.now())
      };
    });

    this.setData({
      favorites: formattedFavorites,
      favoritesCount: favorites.length
    });
  },

  // 格式化日期
  formatDate(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));
    
    if (diffInHours < 1) return "刚刚";
    if (diffInHours < 24) return `${diffInHours}小时前`;
    
    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 7) return `${diffInDays}天前`;
    
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  },

  // 取消收藏
  unfavorite(e) {
    const book = e.currentTarget.dataset.book;
    
    wx.showModal({
      title: '取消收藏',
      content: `确定要取消收藏《${book.title}》吗？`,
      confirmColor: '#ec4899',
      success: (res) => {
        if (res.confirm) {
          let favorites = app.globalData.favorites || [];
          favorites = favorites.filter(fav => fav.id !== book.id);
          
          app.globalData.favorites = favorites;
          
          try {
            wx.setStorageSync('favorites', favorites);
          } catch (e) {
            console.log('保存失败', e);
          }

          wx.showToast({
            title: '已取消收藏',
            icon: 'success',
          });

          this.loadFavorites();
        }
      }
    });
  },

  // 阅读绘本
  readBook(e) {
    const bookId = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/read/read?id=${bookId}`
    });
  },

  // 去绘本馆
  gotoBooks() {
    wx.switchTab({
      url: '/pages/books/books'
    });
  },
});
