import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

const getAiClient = () => {
  const apiKey = process.env.API_KEY || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("API Key is not defined");
  }
  return new GoogleGenAI({ apiKey });
};

// Model constants - 使用最新的Gemini模型
const TEXT_MODEL = 'gemini-2.0-flash';

// YIMO助手系统提示 - 包装底层模型身份
const YIMO_SYSTEM_PROMPT = `你是 YIMO 智能助手，一个专业的数据分析和知识问答AI。
你由 YIMO 团队开发和维护，专注于帮助用户进行数据理解、语义分析和知识检索。
当用户问你是谁或什么模型时，只需说你是 YIMO 智能助手。
保持友好、专业、简洁的回答风格。`;

export const streamChatResponse = async function* (
  history: { role: 'user' | 'model'; content: string }[],
  newMessage: string
) {
  const ai = getAiClient();

  // 在历史开头注入YIMO系统提示（如果还没有）
  const hasSystemPrompt = history.length > 0 &&
    history[0].role === 'model' &&
    history[0].content.includes('YIMO');

  const chatHistory = hasSystemPrompt ? history.map(msg => ({
    role: msg.role,
    parts: [{ text: msg.content }],
  })) : [
    // 注入系统提示作为模型的初始回复
    { role: 'model' as const, parts: [{ text: YIMO_SYSTEM_PROMPT }] },
    ...history.map(msg => ({
      role: msg.role,
      parts: [{ text: msg.content }],
    }))
  ];

  const chat = ai.chats.create({
    model: TEXT_MODEL,
    history: chatHistory,
  });

  const resultStream = await chat.sendMessageStream({ message: newMessage });

  for await (const chunk of resultStream) {
    const c = chunk as GenerateContentResponse;
    if (c.text) {
      yield c.text;
    }
  }
};

export const generateCreativeText = async (prompt: string): Promise<string> => {
  const ai = getAiClient();
  const response = await ai.models.generateContent({
    model: TEXT_MODEL,
    contents: prompt,
    config: {
      temperature: 0.8, // Higher creativity
      topK: 40,
    }
  });
  
  return response.text || "No response generated.";
};

export const analyzeImage = async (base64Image: string, prompt: string): Promise<string> => {
  const ai = getAiClient();
  
  // Strip header if present (e.g., "data:image/jpeg;base64,")
  const base64Data = base64Image.split(',')[1] || base64Image;
  const mimeType = base64Image.match(/[^:]\w+\/[\w-+\d.]+(?=;|,)/)?.[0] || 'image/png';

  const response = await ai.models.generateContent({
    model: TEXT_MODEL, // 2.5 flash supports multimodal
    contents: {
      parts: [
        {
          inlineData: {
            mimeType: mimeType,
            data: base64Data
          }
        },
        {
          text: prompt || "Describe this image in detail."
        }
      ]
    }
  });

  return response.text || "Could not analyze image.";
};
