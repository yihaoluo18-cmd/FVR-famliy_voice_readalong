/**
 * 体验版 / 正式版发布前配置
 * ------------------------
 * 将 onlineApiBaseUrl 设为微信云托管或已备案 HTTPS 的根地址（无尾斜杠），
 * 例如：https://your-service-xxx.ap-shanghai.tcloudbaseapp.com
 *
 * 留空时：走 app 全局 / 本地存储 apiBaseUrl，未配置则回退本机 9880（仅开发者工具/局域网调试）。
 */
module.exports = {
  onlineApiBaseUrl: "",
};
