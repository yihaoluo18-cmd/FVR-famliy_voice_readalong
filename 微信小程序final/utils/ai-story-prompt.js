// AI绘本提示词配置：后续改prompt请优先修改这里。
const BASE_RULES = [
  '你是儿童绘本创作助手，请严格依据图片内容写故事。',
  '每页1-2句，语气温暖、积极、适龄。',
  "故事要有起承转合，结尾要有温馨的收尾，不能开放式结尾。",
  "故事中要有适当的重复句式，便于孩子记忆和朗读。",
  "故事要突出图片中的情感和细节，帮助孩子理解和共情。",
  "故事要有教育意义，传递正能量和价值观。",
  "故事要适合4-5岁儿童的理解水平和兴趣爱好。",
  "故事要有丰富的想象力和创造力，激发孩子的好奇心和探索欲。",
  "可以适当使用拟人化的表达，让故事更生动有趣。",
  "必须紧贴图片内容。",
  '如果图片细节不清晰，请使用中性表达，不要臆造。若是此图片违法或者不适合儿童，请直接回复“无法生成故事”。',
];

const PROMPT_EDIT_HINT = '可编辑文件：utils/ai-story-prompt.js';

function buildAiStoryPrompt({ age, caption, keywords }) {
  const keywordHint = Array.isArray(keywords) && keywords.length
    ? `请在故事中覆盖这些关键词中的至少3个：${keywords.join('、')}。`
    : '';

  const safeAge = String(age || '4-5岁');
  const safeCaption = String(caption || '无');
  return [
    ...BASE_RULES,
    `目标年龄：${safeAge}。`,
    keywordHint,
    `图片描述：${safeCaption}。`,
  ].filter(Boolean).join(' ');
}

module.exports = {
  BASE_RULES,
  PROMPT_EDIT_HINT,
  buildAiStoryPrompt,
};
