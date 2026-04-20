/**
 * 伴宠 3D 视角调参（与 @仓库/微信小程序final 约定一致）
 *
 * - 读：GET /ar_companion/pet/companion/state（见 utils/pet-growth.js）
 * - 写：POST /ar_companion/pet/companion/set_view_tuning，body.view_scope 为 pet_detail | home | companion
 *
 * 后端三套全局 map 对应 output/ar_companion_pet_companion_store.json 内：
 * global_form_view_tuning、global_form_view_tuning_home、global_form_view_tuning_companion
 */

const FORM_VIEW_TUNING_KEYS = Object.freeze(["egg", "tier1", "tier2", "tier3"]);

/** 解包 companion/state 响应（兼容 { data: { ... } }） */
function unwrapCompanionStateBody(state) {
  const s = state && typeof state === "object" ? state : {};
  return s.data && typeof s.data === "object" ? s.data : s;
}

function pickFormViewMap(src) {
  if (src && typeof src === "object" && !Array.isArray(src)) return { ...src };
  return {};
}

/**
 * 伴读页「有效调参」合并：pet_detail < home < companion（后者覆盖前者）。
 * 与 pages/companion/companion.js 原 syncCompanion3DFromGlobal 注释一致；保存伴读调参时只应写 companion。
 */
function mergeCompanionPageFormViewTuningFromStateBody(d) {
  const body = d && typeof d === "object" ? d : {};
  const rawPet = pickFormViewMap(body.form_view_tuning);
  const rawHome = pickFormViewMap(body.form_view_tuning_home);
  const rawCmp = pickFormViewMap(body.form_view_tuning_companion);
  return { ...rawPet, ...rawHome, ...rawCmp };
}

module.exports = {
  FORM_VIEW_TUNING_KEYS,
  unwrapCompanionStateBody,
  mergeCompanionPageFormViewTuningFromStateBody,
};
