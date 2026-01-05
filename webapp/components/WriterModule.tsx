import React, { useState } from 'react';
import { PenTool, Sparkles, Copy, Check, RefreshCw, Feather } from 'lucide-react';
import { generateCreativeText } from '../services/geminiService';
import { WriterConfig } from '../types';

const WriterModule: React.FC = () => {
  const [config, setConfig] = useState<WriterConfig>({
    topic: '',
    tone: 'Professional',
    format: 'Blog Post',
    length: 'medium'
  });
  const [result, setResult] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    if (!config.topic) return;
    
    setIsLoading(true);
    setResult('');
    
    const prompt = `
      Act as a professional copywriter.
      Topic: ${config.topic}
      Tone: ${config.tone}
      Format: ${config.format}
      Length: ${config.length}
      
      Please generate high-quality, engaging content based on these parameters.
    `;

    try {
      const text = await generateCreativeText(prompt);
      setResult(text);
    } catch (error) {
      setResult("Error generating content. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result) return;
    navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-7xl mx-auto h-full flex flex-col lg:flex-row gap-6 pb-6">
      {/* Left Panel: Configuration */}
      <div className="w-full lg:w-1/3 flex flex-col gap-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2.5 bg-indigo-500/20 rounded-xl text-indigo-400">
             <PenTool className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Creative Writer</h2>
            <p className="text-xs text-slate-400">AI-powered content generation</p>
          </div>
        </div>

        <div className="glass-panel p-6 rounded-2xl space-y-6 flex-1 overflow-y-auto custom-scrollbar">
          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Topic / Subject</label>
            <textarea
              value={config.topic}
              onChange={(e) => setConfig(prev => ({ ...prev, topic: e.target.value }))}
              placeholder="What should I write about today?"
              className="w-full glass-input rounded-xl p-4 text-white focus:outline-none resize-none h-32 text-sm leading-relaxed placeholder:text-slate-600"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Tone</label>
              <div className="relative">
                <select 
                  value={config.tone}
                  onChange={(e) => setConfig(prev => ({ ...prev, tone: e.target.value }))}
                  className="w-full appearance-none glass-input rounded-xl px-4 py-3 text-white focus:outline-none text-sm cursor-pointer"
                >
                  <option className="bg-slate-900 text-white">Professional</option>
                  <option className="bg-slate-900 text-white">Casual</option>
                  <option className="bg-slate-900 text-white">Enthusiastic</option>
                  <option className="bg-slate-900 text-white">Witty</option>
                  <option className="bg-slate-900 text-white">Empathetic</option>
                </select>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Format</label>
              <div className="relative">
                <select 
                  value={config.format}
                  onChange={(e) => setConfig(prev => ({ ...prev, format: e.target.value }))}
                  className="w-full appearance-none glass-input rounded-xl px-4 py-3 text-white focus:outline-none text-sm cursor-pointer"
                >
                  <option className="bg-slate-900 text-white">Blog Post</option>
                  <option className="bg-slate-900 text-white">Email</option>
                  <option className="bg-slate-900 text-white">Social Caption</option>
                  <option className="bg-slate-900 text-white">Product Desc</option>
                  <option className="bg-slate-900 text-white">Essay</option>
                </select>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>
            </div>
          </div>

           <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Length</label>
              <div className="flex bg-slate-900/50 p-1.5 rounded-xl border border-white/5">
                {['short', 'medium', 'long'].map((len) => (
                  <button
                    key={len}
                    onClick={() => setConfig(prev => ({ ...prev, length: len as any }))}
                    className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all uppercase tracking-wide ${
                      config.length === len 
                        ? 'bg-indigo-600 text-white shadow-md' 
                        : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                    }`}
                  >
                    {len}
                  </button>
                ))}
              </div>
            </div>

          <button
            onClick={handleGenerate}
            disabled={!config.topic || isLoading}
            className="w-full py-4 bg-gradient-to-r from-indigo-600 to-violet-600 hover:shadow-lg hover:shadow-indigo-500/25 active:scale-[0.98] text-white rounded-xl font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-4 group"
          >
            {isLoading ? (
              <RefreshCw className="w-5 h-5 animate-spin" />
            ) : (
              <>
                <Sparkles className="w-5 h-5 group-hover:text-yellow-200 transition-colors" />
                <span>Generate Content</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Right Panel: Output */}
      <div className="flex-1 glass-panel rounded-2xl p-8 flex flex-col relative overflow-hidden min-h-[500px] lg:min-h-0 shadow-2xl shadow-black/20">
        {result ? (
          <>
            <div className="absolute top-6 right-6 flex gap-2 z-10">
               <button 
                onClick={handleCopy}
                className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 hover:bg-indigo-600 text-slate-300 hover:text-white rounded-lg transition-all text-xs font-medium border border-white/5 backdrop-blur-md"
              >
                {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied' : 'Copy Text'}
              </button>
            </div>
            <div className="overflow-y-auto custom-scrollbar flex-1 pr-2 pt-2">
              <div className="prose prose-invert prose-lg max-w-none">
                <p className="whitespace-pre-wrap leading-relaxed text-slate-200 font-light">{result}</p>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-600">
            <div className="w-24 h-24 rounded-full bg-slate-900/50 flex items-center justify-center mb-6 border border-slate-800">
              <Feather className="w-10 h-10 text-slate-700" />
            </div>
            <h3 className="text-xl font-semibold text-slate-500 mb-2">Canvas Empty</h3>
            <p className="text-sm max-w-xs text-center text-slate-600">Configure your settings on the left and let the AI craft your masterpiece.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default WriterModule;