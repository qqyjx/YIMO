import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Trash2, StopCircle, Sparkles } from 'lucide-react';
import { Message } from '../types';
import { streamChatResponse } from '../services/geminiService';

const ChatModule: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'model',
      content: "你好！我是 YIMO 智能助手。我可以帮助你分析数据、回答问题或进行创意写作。今天有什么可以帮你的吗？",
      timestamp: Date.now()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    
    const modelMsgId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, {
      id: modelMsgId,
      role: 'model',
      content: '',
      timestamp: Date.now()
    }]);

    try {
      let fullText = '';
      for await (const chunk of streamChatResponse(history, userMsg.content)) {
        fullText += chunk;
        setMessages(prev => prev.map(msg => 
          msg.id === modelMsgId ? { ...msg, content: fullText } : msg
        ));
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => prev.map(msg => 
        msg.id === modelMsgId 
          ? { ...msg, content: "I apologize, but I encountered an error processing your request.", isError: true } 
          : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full max-w-5xl mx-auto relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 md:mb-4 px-2 md:px-0 flex-shrink-0">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            YIMO 智能助手 <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-medium">AI</span>
          </h2>
          <p className="text-slate-400 text-sm hidden md:block">智能对话与数据分析</p>
        </div>
        <button 
          onClick={() => setMessages([])}
          className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-400/10 rounded-xl transition-colors"
          title="Clear conversation"
        >
          <Trash2 className="w-5 h-5" />
        </button>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-2 md:pr-4 mb-20 md:mb-24 scroll-smooth no-scrollbar md:custom-scrollbar">
        {messages.length === 0 && (
           <div className="h-full flex flex-col items-center justify-center opacity-50">
             <Bot className="w-16 h-16 text-slate-600 mb-4" />
             <p className="text-slate-500">Start a new conversation</p>
           </div>
        )}
        
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`}
          >
            {msg.role === 'model' && (
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg shadow-indigo-500/20">
                <Bot className="w-5 h-5 text-white" />
              </div>
            )}
            
            <div
              className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-5 py-3.5 leading-relaxed shadow-sm ${
                msg.role === 'user'
                  ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white rounded-tr-sm'
                  : msg.isError
                    ? 'bg-red-900/20 border border-red-500/30 text-red-200 rounded-tl-sm backdrop-blur-sm'
                    : 'glass-panel text-slate-200 rounded-tl-sm'
              }`}
            >
              <div className="whitespace-pre-wrap text-[15px]">
                {msg.content || (isLoading && msg.id === messages[messages.length - 1].id ? (
                  <span className="flex items-center gap-1">
                    Thinking <span className="animate-pulse">...</span>
                  </span>
                ) : '')}
              </div>
            </div>

            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-xl bg-slate-700/50 border border-slate-600 flex items-center justify-center flex-shrink-0 mt-1">
                <User className="w-5 h-5 text-slate-300" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area - Floating & Glassmorphic */}
      <div className="absolute bottom-0 left-0 right-0 pb-4 md:pb-6 px-2 md:px-0 bg-gradient-to-t from-[#020617] via-[#020617] to-transparent pt-10">
        <div className="relative glass-panel rounded-2xl p-1.5 flex items-end shadow-2xl shadow-black/50">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={isLoading}
            className="w-full bg-transparent text-white rounded-xl pl-4 pr-4 py-3.5 focus:outline-none resize-none max-h-32 min-h-[56px] text-[15px] placeholder:text-slate-500"
            style={{ height: '56px' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className={`mb-1.5 mr-1.5 p-2.5 rounded-xl flex-shrink-0 transition-all duration-200 ${
              input.trim() && !isLoading 
                ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/30 active:scale-95' 
                : 'bg-slate-700/50 text-slate-500 cursor-not-allowed'
            }`}
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
        <div className="text-center mt-2">
          <p className="text-[10px] text-slate-600">AI responses may vary. Double-check important information.</p>
        </div>
      </div>
    </div>
  );
};

export default ChatModule;