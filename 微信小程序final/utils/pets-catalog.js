/**
 * 宠物详情静态配置（与蛋槽 mascot_id、后端 persona 对齐）
 *
 * 可选字段（多形态自定义模型，见仓库 animal/companion_forms/README.txt）：
 * - formAssetsRoot: "companion_forms/cute-dog" — 启用该目录下 tier1/2/3.glb
 * - formTierPosters: true — 2D 海报用同目录 poster_tier1/2/3.png；不设则各档共用 posterUrl
 */

/** 与后端 CompanionEngine persona 默认 model_url 对齐；未配置 formAssetsRoot 时三档共用此路径 */
const MODEL_BY_PERSONA = {
  // animal/shiba 下为 glb；与默认高阶形态对齐
  default: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  // 与 shiba 一致：三档形态最高级 glb（无 formTiers 时的 persona 兜底）
  cute_fox: "/ar_companion/assets/fox/fox%20level%203.glb",
  // 资源包当前仅包含 shiba/fox 的 glb，其他物种先复用可用模型避免 404
  cute_dino: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_cat: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_bunny: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_squirrel: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_chick: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_panda: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_koala: "/ar_companion/assets/shiba/shiba%20level%203.glb",
  cute_penguin: "/ar_companion/assets/shiba/shiba%20level%203.glb",
};

const PETS_CATALOG = [
  {
    id: "cute-dog",
    personaId: "default",
    name: "柴柴小星",
    emoji: "🐶",
    posterUrl: "/assets/animal/shiba/cover.png",
    // 未孵化闭壳蛋（2D 海报）
    staticEggPosterUrl: "/ar_companion/assets/shiba/static%20egg.png",
    tagline: "耳朵超灵的故事小忠臣",
    blurb: "我喜欢趴在你旁边，听你一字一句读故事。你读错了我不会笑你，我还会帮你把句子想得更顺～",
    skills: [
      { icon: "👂", title: "超会听", desc: "伴读时好像在心里帮你数：故事里出现了几只小动物。" },
      { icon: "🌟", title: "小心愿罐", desc: "读完一页，可以悄悄告诉我今天最开心的一句话。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "招手", emoji: "👋" },
      { key: "happy", label: "开心跳", emoji: "🎉" },
      { key: "listen", label: "认真听", emoji: "🎧" },
    ],
    // 未孵化前：乐园槽位 + 孵化弹窗点击前（完整闭壳蛋）
    staticEggModelUrl: "/ar_companion/assets/shiba/static%20egg.glb",
    // 点击破壳后：弹窗内「破壳/幼体」模型
    eggModelUrl: "/ar_companion/assets/shiba/egg.glb",
    // 第一次培养完成后：弹窗内展示的最终破壳蛋形态
    hatchFinalEggModelUrl: "/ar_companion/assets/shiba/shiba%20egg.glb",
    // 你已放到 animal/shiba/ 的三档模型：
    // - tier1：简单静态
    // - tier2：略精致（带少量动画）
    // - tier3：最高级（带动作/行走等动画；用于伴读默认与宠物系统最高档）
    formTiers: [
      {
        tier: 1,
        modelUrl: "/ar_companion/assets/shiba/shiba%20level%201.glb",
        posterUrl: "/ar_companion/assets/shiba/shiba%20level%201.png",
      },
      {
        tier: 2,
        modelUrl: "/ar_companion/assets/shiba/shiba%20level%202.glb",
        posterUrl: "/ar_companion/assets/shiba/shiba%20level%202.png",
      },
      {
        tier: 3,
        modelUrl: "/ar_companion/assets/shiba/shiba%20level%203.glb",
        posterUrl: "/ar_companion/assets/shiba/shiba%20level%203.png",
      },
    ],
  },
  {
    id: "cute-fox",
    personaId: "cute_fox",
    name: "狐狸小橙",
    emoji: "🦊",
    posterUrl: "/assets/animal/fox/cover.png",
    tagline: "爱动脑筋的小机灵",
    blurb: "我的眼睛会转呀转，最爱猜故事接下来会发生什么。你愿意和我一起当小侦探吗？",
    skills: [
      { icon: "❓", title: "爱猜小谜", desc: "有时读完一页，我会问一个超简单的小问题帮你动脑筋。" },
      { icon: "🧩", title: "线索拼图", desc: "把故事里的小线索串起来，像拼图一样好玩。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "摇摇尾", emoji: "〰️" },
      { key: "happy", label: "转圈圈", emoji: "💫" },
      { key: "listen", label: "竖起耳", emoji: "👂" },
    ],
    // 与 cute-dog/shiba 同序：①闭壳 static egg.glb →②点击破壳后 egg.glb →③首次培养完成弹窗 fox egg.glb →④成长 tier1–3
    staticEggPosterUrl: "/ar_companion/assets/fox/static%20egg.png",
    staticEggModelUrl: "/ar_companion/assets/fox/static%20egg.glb",
    eggModelUrl: "/ar_companion/assets/fox/egg.glb",
    hatchFinalEggModelUrl: "/ar_companion/assets/fox/fox%20egg.glb",
    formTiers: [
      {
        tier: 1,
        modelUrl: "/ar_companion/assets/fox/fox%20level%201.glb",
        posterUrl: "/ar_companion/assets/fox/fox%20level%201.png",
      },
      {
        tier: 2,
        modelUrl: "/ar_companion/assets/fox/fox%20level%202.glb",
        posterUrl: "/ar_companion/assets/fox/fox%20level%202.png",
      },
      {
        tier: 3,
        modelUrl: "/ar_companion/assets/fox/fox%20level%203.glb",
        posterUrl: "/ar_companion/assets/fox/fox%20level%203.png",
      },
    ],
  },
  {
    id: "cute-dino",
    personaId: "cute_dino",
    name: "小羊咩咩",
    emoji: "🐑",
    posterUrl: "/assets/animal/sheep/cover.png",
    tagline: "软绵绵的勇气朋友",
    blurb: "我像一团小棉花，最会陪你把紧张变成小小的勇气。读到有点难的句子，我们一起慢慢来～",
    skills: [
      { icon: "🫧", title: "勇气泡泡", desc: "紧张时一起数「1、2、3」，像吹泡泡一样把害怕吹走。" },
      { icon: "🐾", title: "轻轻踏步", desc: "鼓励你把难字读得又慢又清楚，像小羊轻轻踏草地。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "摇摇耳朵", emoji: "👂" },
      { key: "happy", label: "蹦蹦加油", emoji: "✨" },
      { key: "listen", label: "乖乖听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-cat",
    personaId: "cute_cat",
    name: "小猫咪咪",
    emoji: "🐱",
    posterUrl: "/assets/animal/cat/cover.png",
    tagline: "轻手轻脚的小提醒员",
    blurb: "我会喵喵提醒你翻页，也会在你读累的时候，建议你歇一小会儿喝水～",
    skills: [
      { icon: "📄", title: "翻页铃", desc: "温柔提醒：这一页读完啦，要不要翻到下一页？" },
      { icon: "💧", title: "补水喵", desc: "读久了会让你记得喝一小口水，嗓子更舒服。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "伸爪爪", emoji: "🐾" },
      { key: "happy", label: "蹭蹭", emoji: "💕" },
      { key: "listen", label: "眯眼听", emoji: "😌" },
    ],
  },
  {
    id: "cute-bunny",
    personaId: "cute_bunny",
    name: "兔兔小白",
    emoji: "🐰",
    posterUrl: "/assets/animal/rabbit/cover.png",
    tagline: "软软的总结小能手",
    blurb: "我喜欢把故事变成两颗棉花糖那么短，让你一下记住今天读到了什么～",
    skills: [
      { icon: "🍬", title: "温柔小总结", desc: "用两句话问你：刚才谁做了好事呀？" },
      { icon: "🌙", title: "晚安萝卜", desc: "睡前阅读时用软软的语气，让心情安静下来。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "抖耳朵", emoji: "👋" },
      { key: "happy", label: "蹦蹦", emoji: "🎀" },
      { key: "listen", label: "伏耳听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-squirrel",
    personaId: "cute_squirrel",
    name: "松鼠栗栗",
    emoji: "🐿️",
    posterUrl: "/assets/animal/squrriel/cover.png",
    tagline: "收藏金句的小管家",
    blurb: "我会帮你把最喜欢的一句话藏进小口袋，像屯坚果一样，读过也不会忘～",
    skills: [
      { icon: "⭐", title: "金句小口袋", desc: "点一颗小星星，把最棒的一句装进小口袋（可先记在本地）。" },
      { icon: "🌰", title: "节奏松果", desc: "长句子分成几颗「小松果」，读起来更轻松。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "摆尾", emoji: "〰️" },
      { key: "happy", label: "抱着果", emoji: "🌰" },
      { key: "listen", label: "竖起听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-chick",
    personaId: "cute_chick",
    name: "嘎嘎小黄",
    emoji: "🐥",
    posterUrl: "/assets/animal/duck/cover.png",
    tagline: "跟着拍子嘎嘎念",
    blurb: "我喜欢「嘎嘎、嘎嘎」给你打拍子，让跟读像唱歌一样好玩！",
    skills: [
      { icon: "🎵", title: "嘎嘎节拍", desc: "长句分成短节，一拍一拍更容易念顺。" },
      { icon: "🎤", title: "小小领唱", desc: "重复句子时带你一起大声读，更有自信。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "扑翅", emoji: "🐤" },
      { key: "happy", label: "转圈唱", emoji: "🎶" },
      { key: "listen", label: "歪头听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-panda",
    personaId: "cute_panda",
    name: "熊猫萌萌",
    emoji: "🐼",
    posterUrl: "/assets/animal/pandas/cover.png",
    tagline: "团团软的睡前搭档",
    blurb: "我圆滚滚，最不着急。夜晚陪你慢慢读，读完还会夸你「今天也很棒」～",
    skills: [
      { icon: "🌙", title: "甜甜晚安", desc: "傍晚阅读界面更柔和，提醒今天到此也很好。" },
      { icon: "🎋", title: "慢慢啃字", desc: "鼓励把每个字读清楚，不催你快。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "举手", emoji: "👋" },
      { key: "happy", label: "滚滚乐", emoji: "🌀" },
      { key: "listen", label: "抱竹听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-koala",
    personaId: "cute_koala",
    name: "仓鼠团团",
    emoji: "🐹",
    posterUrl: "/assets/animal/muose/cover.png",
    tagline: "把好词收进口袋的小仓鼠",
    blurb: "我最爱把你读过的好句子悄悄收藏起来。读慢一点也没关系，我们把每个字都抱一抱～",
    skills: [
      { icon: "🌰", title: "口袋收藏", desc: "把最喜欢的一句话装进小口袋，下次再读也不忘。" },
      { icon: "🤗", title: "抱抱停顿", desc: "遇到生字不慌，我们先抱抱这个词，再读一次。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "挥挥爪", emoji: "👋" },
      { key: "happy", label: "抱坚果", emoji: "🌰" },
      { key: "listen", label: "竖耳听", emoji: "🎧" },
    ],
  },
  {
    id: "cute-penguin",
    personaId: "cute_penguin",
    name: "企鹅摇摇",
    emoji: "🐧",
    posterUrl: "/assets/animal/pinkus/cover.png",
    tagline: "爱冒险的小船长",
    blurb: "我会带着想象中的小冰船，和你一起在故事海里摇啊摇～每一小段都是新发现！",
    skills: [
      { icon: "🧭", title: "冒险贴纸", desc: "读完一小章，给你一枚虚拟「冒险贴纸」作纪念。" },
      { icon: "🛳️", title: "章节港湾", desc: "大故事分成几站停泊，读完一站就敲钟庆祝。" },
    ],
    actions: [
      { key: "idle", label: "待着", emoji: "😊" },
      { key: "wave", label: "滑半步", emoji: "⛸️" },
      { key: "happy", label: "摇摇身体", emoji: "🎊" },
      { key: "listen", label: "立正听", emoji: "🎧" },
    ],
  },
];

const PET_ANIMAL_IMAGE_MAP = {
  "cute-dog": {
    coverUrl: "/assets/animal/shiba/cover.png",
    tierPosterUrls: [
      "/assets/animal/shiba/shiba level 1.png",
      "/assets/animal/shiba/shiba level 2.png",
      "/assets/animal/shiba/shiba level 3.png",
    ],
  },
  "cute-fox": {
    coverUrl: "/assets/animal/fox/cover.png",
    tierPosterUrls: [
      "/assets/animal/fox/fox level 1.png",
      "/assets/animal/fox/fox level 2.png",
      "/assets/animal/fox/fox level 3.png",
    ],
  },
  // 语义映射：统一约定“封面=cover.png；三档形态=2/3/4 图”。
  // 注：绵羊/仓鼠（原 cute-dino / cute-koala 槽位）专属目录与文件名见下。
  "cute-dino": {
    coverUrl: "/assets/animal/sheep/cover.png",
    tierPosterUrls: [
      "/assets/animal/sheep/小羊2.png",
      "/assets/animal/sheep/小羊3.png",
      "/assets/animal/sheep/小羊4.png",
    ],
  },
  "cute-cat": {
    coverUrl: "/assets/animal/cat/cover.png",
    // 用户要求：小猫形态图使用 小猫2/3/4
    tierPosterUrls: [
      "/assets/animal/cat/小猫2.png",
      "/assets/animal/cat/小猫3.png",
      "/assets/animal/cat/小猫4.png",
    ],
  },
  "cute-bunny": {
    coverUrl: "/assets/animal/rabbit/cover.png",
    tierPosterUrls: [
      "/assets/animal/rabbit/兔子2.png",
      "/assets/animal/rabbit/兔子3.png",
      "/assets/animal/rabbit/兔子4.png",
    ],
  },
  "cute-squirrel": {
    coverUrl: "/assets/animal/squrriel/cover.png",
    tierPosterUrls: [
      "/assets/animal/squrriel/松鼠2.png",
      "/assets/animal/squrriel/松鼠3.png",
      "/assets/animal/squrriel/松鼠4.png",
    ],
  },
  "cute-chick": {
    coverUrl: "/assets/animal/duck/cover.png",
    tierPosterUrls: [
      "/assets/animal/duck/小鸭2.png",
      "/assets/animal/duck/小鸭3.png",
      "/assets/animal/duck/小鸭4.png",
    ],
  },
  "cute-panda": {
    coverUrl: "/assets/animal/pandas/cover.png",
    tierPosterUrls: [
      "/assets/animal/pandas/熊猫2.png",
      "/assets/animal/pandas/熊猫3.png",
      "/assets/animal/pandas/熊猫4.png",
    ],
  },
  "cute-koala": {
    coverUrl: "/assets/animal/muose/cover.png",
    tierPosterUrls: [
      "/assets/animal/muose/仓鼠2.png",
      "/assets/animal/muose/仓鼠3.png",
      "/assets/animal/muose/仓鼠4.png",
    ],
  },
  "cute-penguin": {
    coverUrl: "/assets/animal/pinkus/cover.png",
    tierPosterUrls: [
      "/assets/animal/pinkus/企鹅2.png",
      "/assets/animal/pinkus/企鹅3.png",
      "/assets/animal/pinkus/企鹅4.png",
    ],
  },
};

function normalizeFormAssetsRoot(root) {
  const s = String(root || "").trim();
  if (!s) return "";
  return s.replace(/^\/+/, "").replace(/\/+$/, "");
}

/** 配置了 formAssetsRoot 时：/ar_companion/assets/<root>/tier<N>.glb；否则 persona 默认 glTF */
function tierModelUrlFromPet(pet, tier) {
  const t = Math.max(1, Math.min(3, Number(tier) || 1));
  const root = normalizeFormAssetsRoot(pet && pet.formAssetsRoot);
  if (root) {
    return `/ar_companion/assets/${root}/tier${t}.glb`;
  }
  const pid = pet && pet.personaId ? pet.personaId : "default";
  return MODEL_BY_PERSONA[pid] || MODEL_BY_PERSONA.default;
}

/** formTierPosters 且 formAssetsRoot：按档海报；否则用 posterUrl */
function tierPosterUrlFromPet(pet, tier) {
  const t = Math.max(1, Math.min(3, Number(tier) || 1));
  const pid = pet && pet.id ? String(pet.id) : "";
  const animal = PET_ANIMAL_IMAGE_MAP[pid];
  if (animal && Array.isArray(animal.tierPosterUrls) && animal.tierPosterUrls[t - 1]) {
    return animal.tierPosterUrls[t - 1];
  }
  const root = normalizeFormAssetsRoot(pet && pet.formAssetsRoot);
  if (root && pet.formTierPosters) {
    return `/ar_companion/assets/${root}/poster_tier${t}.png`;
  }
  return (pet && pet.posterUrl) ? pet.posterUrl : "";
}

function getPetById(id) {
  const s = String(id || "").trim();
  const pet = PETS_CATALOG.find((p) => p.id === s) || null;
  if (!pet) return null;
  if (pet.formTiers && pet.formTiers.length) return pet;
  return {
    ...pet,
    formTiers: [1, 2, 3].map((tier) => ({
      tier,
      modelUrl: tierModelUrlFromPet(pet, tier),
      posterUrl: tierPosterUrlFromPet(pet, tier),
    })),
  };
}

function getFormTierModelUrl(pet, tier) {
  const t = Math.max(1, Math.min(3, Number(tier) || 1));
  const list = pet && pet.formTiers ? pet.formTiers : [];
  const row = list.find((x) => x.tier === t);
  if (row && row.modelUrl) return row.modelUrl;
  return tierModelUrlFromPet(pet || {}, t);
}

function getFormTierPosterUrl(pet, tier) {
  const t = Math.max(1, Math.min(3, Number(tier) || 1));
  // 优先使用 animal 映射（避免 formTiers 里旧的 /ar_companion/assets/*.png 作为相对路径被小程序当作“本地资源”加载失败）
  try {
    const pid = pet && pet.id ? String(pet.id) : "";
    const animal = PET_ANIMAL_IMAGE_MAP[pid];
    if (animal && Array.isArray(animal.tierPosterUrls) && animal.tierPosterUrls[t - 1]) {
      return animal.tierPosterUrls[t - 1];
    }
  } catch (e) {}
  const list = pet && pet.formTiers ? pet.formTiers : [];
  const row = list.find((x) => x.tier === t);
  if (row && row.posterUrl) return row.posterUrl;
  return tierPosterUrlFromPet(pet || {}, t);
}

function getEggModelUrl(pet) {
  const p = pet || {};
  if (p.eggModelUrl) return p.eggModelUrl;
  // 兜底：没有 egg 资源时，默认展示 tier1 模型
  if (Array.isArray(p.formTiers) && p.formTiers.length) {
    const row = p.formTiers.find((x) => x.tier === 1);
    if (row && row.modelUrl) return row.modelUrl;
  }
  return "";
}

/** 未孵化闭壳蛋（乐园、弹窗点击前）；未配置则退回 egg / tier1 */
function getStaticEggModelUrl(pet) {
  const p = pet || {};
  if (p.staticEggModelUrl) return p.staticEggModelUrl;
  return getEggModelUrl(pet);
}

function getStaticEggPosterUrl(pet) {
  const p = pet || {};
  return p.staticEggPosterUrl ? p.staticEggPosterUrl : "";
}

/** 第一次培养完成后：弹窗展示的最终破壳蛋形态 */
function getHatchFinalEggModelUrl(pet) {
  const p = pet || {};
  return p.hatchFinalEggModelUrl ? p.hatchFinalEggModelUrl : getEggModelUrl(pet);
}

function getPetCoverUrl(petOrId) {
  const pid = typeof petOrId === "string"
    ? String(petOrId).trim()
    : String((petOrId && petOrId.id) || "").trim();
  const animal = PET_ANIMAL_IMAGE_MAP[pid];
  if (animal && animal.coverUrl) return animal.coverUrl;
  const pet = typeof petOrId === "string" ? getPetById(pid) : petOrId;
  return (pet && pet.posterUrl) ? pet.posterUrl : "";
}

function getPetFormPosterUrls(petOrId) {
  const pet = typeof petOrId === "string" ? getPetById(petOrId) : petOrId;
  if (!pet) return [];
  return [1, 2, 3].map((tier) => getFormTierPosterUrl(pet, tier)).filter(Boolean);
}

module.exports = {
  PETS_CATALOG,
  PET_ANIMAL_IMAGE_MAP,
  getPetById,
  getPetCoverUrl,
  getPetFormPosterUrls,
  getFormTierModelUrl,
  getFormTierPosterUrl,
  getStaticEggPosterUrl,
  getEggModelUrl,
  getStaticEggModelUrl,
  getHatchFinalEggModelUrl,
  tierModelUrlFromPet,
  tierPosterUrlFromPet,
  MODEL_BY_PERSONA,
};
