import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

const getAiClient = () => {
  const apiKey = process.env.API_KEY;
  if (!apiKey) {
    throw new Error("API Key is not defined");
  }
  return new GoogleGenAI({ apiKey });
};

// Model constants
const TEXT_MODEL = 'gemini-2.5-flash';

export const streamChatResponse = async function* (
  history: { role: 'user' | 'model'; content: string }[],
  newMessage: string
) {
  const ai = getAiClient();
  // Transform simple history to ChatSession format if needed, 
  // but for simple turns, we can use sendMessageStream on a chat object.
  // To keep it stateless for this demo, we re-init chat with history.
  
  const chatHistory = history.map(msg => ({
    role: msg.role,
    parts: [{ text: msg.content }],
  }));

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
