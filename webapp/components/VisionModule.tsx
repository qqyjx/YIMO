import React, { useState, useRef } from 'react';
import { Upload, Image as ImageIcon, X, Search, Loader2, Eye, ScanLine } from 'lucide-react';
import { analyzeImage } from '../services/geminiService';
import { VisionState } from '../types';

const VisionModule: React.FC = () => {
  const [state, setState] = useState<VisionState>({
    image: null,
    analysis: null,
    isLoading: false
  });
  const [prompt, setPrompt] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  };

  const processFile = (file: File) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      setState({
        image: reader.result as string,
        analysis: null,
        isLoading: false
      });
    };
    reader.readAsDataURL(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleAnalyze = async () => {
    if (!state.image) return;

    setState(prev => ({ ...prev, isLoading: true, analysis: null }));
    
    try {
      const result = await analyzeImage(state.image, prompt);
      setState(prev => ({ ...prev, analysis: result }));
    } catch (error) {
      console.error(error);
      setState(prev => ({ ...prev, analysis: "Failed to analyze the image. Please try again." }));
    } finally {
      setState(prev => ({ ...prev, isLoading: false }));
    }
  };

  const clearImage = () => {
    setState({ image: null, analysis: null, isLoading: false });
    setPrompt('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="max-w-6xl mx-auto h-full flex flex-col">
      <div className="mb-6">
         <h2 className="text-2xl font-bold text-white tracking-tight">Vision Analysis</h2>
         <p className="text-slate-400 text-sm mt-1">Upload images for instant AI recognition and description</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1 min-h-0 pb-6">
        {/* Left Column: Input Area */}
        <div className="flex flex-col gap-4 h-full">
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative flex-1 min-h-[300px] rounded-2xl transition-all duration-300 flex flex-col items-center justify-center overflow-hidden group border-2 border-dashed ${
              state.image 
                ? 'border-slate-700 bg-slate-900' 
                : isDragging
                  ? 'border-indigo-500 bg-indigo-500/10'
                  : 'border-slate-700/50 bg-slate-800/20 hover:border-indigo-500/30 hover:bg-slate-800/40'
            }`}
          >
            {!state.image ? (
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="text-center cursor-pointer p-8 w-full h-full flex flex-col items-center justify-center"
              >
                <div className={`w-20 h-20 rounded-full flex items-center justify-center mb-6 transition-all duration-300 ${isDragging ? 'bg-indigo-500/20 scale-110' : 'bg-slate-800/50 group-hover:scale-105'}`}>
                  <Upload className={`w-8 h-8 ${isDragging ? 'text-indigo-400' : 'text-slate-400'}`} />
                </div>
                <p className="text-xl font-semibold text-slate-200">
                  {isDragging ? 'Drop it here!' : 'Upload Image'}
                </p>
                <p className="text-sm text-slate-500 mt-2">Drag & drop or click to browse</p>
                <div className="mt-6 flex gap-3">
                  <span className="px-3 py-1 rounded-full bg-slate-800 text-xs text-slate-400 border border-slate-700">JPG</span>
                  <span className="px-3 py-1 rounded-full bg-slate-800 text-xs text-slate-400 border border-slate-700">PNG</span>
                  <span className="px-3 py-1 rounded-full bg-slate-800 text-xs text-slate-400 border border-slate-700">WEBP</span>
                </div>
              </div>
            ) : (
              <div className="relative w-full h-full bg-slate-950">
                 <img 
                  src={state.image} 
                  alt="Preview" 
                  className="w-full h-full object-contain" 
                />
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                <button 
                  onClick={clearImage}
                  className="absolute top-4 right-4 p-2 bg-black/60 hover:bg-red-500 text-white rounded-xl backdrop-blur-md transition-all opacity-0 group-hover:opacity-100 transform translate-y-2 group-hover:translate-y-0"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            )}
            <input 
              type="file" 
              ref={fileInputRef}
              onChange={handleFileChange}
              accept="image/*"
              className="hidden"
            />
          </div>

          <div className="glass-panel p-5 rounded-2xl">
            <label className="block text-xs font-semibold text-indigo-300 uppercase tracking-wider mb-3">Custom Instruction</label>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="E.g., 'Extract all text' or 'Describe the colors'..."
                className="flex-1 glass-input text-white rounded-xl px-4 py-3 focus:outline-none placeholder:text-slate-600"
              />
              <button
                onClick={handleAnalyze}
                disabled={!state.image || state.isLoading}
                className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 hover:shadow-lg hover:shadow-indigo-500/25 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-medium transition-all flex items-center justify-center gap-2 min-w-[120px]"
              >
                {state.isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <ScanLine className="w-4 h-4" />
                    <span>Analyze</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Output Area */}
        <div className="glass-panel rounded-2xl p-6 flex flex-col overflow-hidden h-[400px] lg:h-auto relative">
          <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                <ImageIcon className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-slate-200">Analysis Results</h3>
            </div>
            {state.analysis && (
              <span className="text-xs text-green-400 bg-green-400/10 px-2 py-1 rounded-full border border-green-400/20">Completed</span>
            )}
          </div>
          
          <div className="flex-1 overflow-y-auto custom-scrollbar pr-2">
            {state.isLoading ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-indigo-500 blur-xl opacity-20 animate-pulse"></div>
                  <Loader2 className="w-10 h-10 animate-spin text-indigo-500 relative z-10" />
                </div>
                <p className="text-sm font-medium animate-pulse text-indigo-300">Processing visual data...</p>
              </div>
            ) : state.analysis ? (
              <div className="prose prose-invert prose-sm max-w-none">
                 <p className="whitespace-pre-wrap leading-relaxed text-slate-300 font-light">{state.analysis}</p>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-slate-600 text-center p-6 border-2 border-dashed border-slate-800 rounded-xl bg-slate-900/30">
                <Eye className="w-12 h-12 text-slate-700 mb-4" />
                <p className="text-slate-400 font-medium">No analysis yet</p>
                <p className="text-sm mt-2 text-slate-600">Upload an image to see AI insights</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default VisionModule;