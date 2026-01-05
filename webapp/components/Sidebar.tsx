import React from 'react';
import { MessageSquare, Eye, PenTool, Sparkles } from 'lucide-react';
import { AppMode } from '../types';

interface SidebarProps {
  currentMode: AppMode;
  setMode: (mode: AppMode) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ currentMode, setMode }) => {
  const navItems = [
    { id: AppMode.CHAT, label: 'AI Chat', icon: MessageSquare, desc: 'Interactive Conversation' },
    { id: AppMode.VISION, label: 'Vision Analysis', icon: Eye, desc: 'Image Recognition' },
    { id: AppMode.WRITER, label: 'Creative Writer', icon: PenTool, desc: 'Content Generation' },
  ];

  return (
    <div className="hidden md:flex flex-col w-72 h-full p-4 border-r border-white/5 bg-slate-900/50 backdrop-blur-xl relative z-20">
      {/* Logo Area */}
      <div className="flex items-center gap-3 mb-10 px-2 pt-2">
        <div className="relative">
          <div className="absolute inset-0 bg-indigo-500 blur opacity-40 rounded-lg"></div>
          <div className="w-10 h-10 relative rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-inner border border-white/10">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
        </div>
        <div>
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400 tracking-tight">
            Lumina
          </h1>
          <span className="text-[10px] uppercase tracking-wider text-indigo-400 font-semibold">AI Studio</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentMode === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setMode(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-all duration-300 group relative overflow-hidden ${
                isActive
                  ? 'bg-white/5 border border-white/10 shadow-lg shadow-black/20'
                  : 'hover:bg-white/5 border border-transparent'
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.5)]" />
              )}
              
              <div className={`p-2 rounded-lg transition-colors ${isActive ? 'bg-indigo-500/20 text-indigo-300' : 'bg-slate-800/50 text-slate-400 group-hover:text-slate-200'}`}>
                <Icon className="w-5 h-5" />
              </div>
              
              <div className="text-left">
                <div className={`font-medium text-sm ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'}`}>
                  {item.label}
                </div>
                <div className="text-[10px] text-slate-500 font-medium">{item.desc}</div>
              </div>
            </button>
          );
        })}
      </nav>

      {/* Footer Card */}
      <div className="mt-auto">
        <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-900/20 to-slate-900/20 border border-indigo-500/10">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs font-medium text-indigo-200">System Operational</span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Powered by Gemini 2.5 Flash. <br/> Optimized for performance.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;