'use client';

import Link from 'next/link';
import { Code, Sparkles, Zap, ArrowRight } from 'lucide-react';
import { useState, useEffect } from 'react';

export const DeveloperBanner = () => {
  const [codeStep, setCodeStep] = useState(0);
  const codeLines = [
    'function createOmiApp() {',
    '  return {',
    '    name: "MyAwesomeApp",',
    '    type: "integration",',
    '    onConversation: (data) => {',
    '      // Your code here',
    '    }',
    '  };',
    '}',
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setCodeStep((prev) => (prev + 1) % codeLines.length);
    }, 1200);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="container mx-auto px-3 sm:px-6 md:px-8">
      <Link
        href="https://docs.omi.me/docs/developer/apps/Introduction"
        target="_blank"
        className="group block w-full transform transition-transform duration-300 hover:scale-[1.01]"
      >
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#2D1B69] to-[#6C2BD9] shadow-lg">
          {/* Background pattern */}
          <div className="absolute inset-0 opacity-10">
            <div className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-white/20"></div>
            <div className="absolute -bottom-8 -left-8 h-40 w-40 rounded-full bg-white/20"></div>
            <div className="absolute bottom-12 right-12 h-24 w-24 rounded-full bg-white/20"></div>
          </div>

          {/* Animated sparkle effect */}
          <div className="absolute right-4 top-4 animate-pulse">
            <Sparkles className="h-5 w-5 text-purple-200/70" />
          </div>

          <div className="relative z-10 flex h-auto flex-col p-6 sm:h-[12rem] sm:flex-row sm:items-center sm:justify-between sm:p-8 md:p-10">
            {/* Left content */}
            <div className="flex flex-col sm:max-w-xs md:max-w-sm">
              <h3 className="text-xl font-bold text-white sm:text-2xl md:text-2xl">
                Start Building Your Own Apps
              </h3>
              <p className="mt-2 text-sm text-purple-100 sm:text-base">
                Create powerful AI-powered apps for Omi and start earning. Join our developer community today!
              </p>
            </div>
            
            {/* Middle - Code typing animation */}
            <div className="mt-4 hidden sm:mt-0 sm:block sm:max-w-md sm:flex-1">
              <div className="h-[9.5rem] overflow-hidden rounded-md bg-black/30 p-3 font-mono text-xs text-purple-200/90 backdrop-blur-sm">
                <div className="h-full">
                  {codeLines.slice(0, codeStep + 1).map((line, i) => (
                    <div key={i} className="whitespace-pre">
                      {line}
                      {i === codeStep && (
                        <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-purple-300"></span>
                      )}
                    </div>
                  ))}
                  {/* Empty lines to maintain height */}
                  {Array(9 - codeStep).fill(0).map((_, i) => (
                    <div key={`empty-${i}`} className="whitespace-pre">&nbsp;</div>
                  ))}
                </div>
              </div>
            </div>
            
            {/* Right - Button */}
            <div className="mt-4 flex items-center sm:ml-4 sm:mt-0">
              <div className="flex items-center gap-1.5 rounded-full bg-black/80 px-4 py-2 text-sm font-medium text-purple-200 shadow-sm transition-all duration-300 group-hover:bg-black group-hover:shadow-md group-hover:shadow-purple-900/30">
                <Zap className="h-3.5 w-3.5" />
                <span>Start Building</span>
                <ArrowRight className="h-3.5 w-3.5 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
              </div>
            </div>
          </div>

          {/* Subtle border glow */}
          <div className="absolute inset-0 rounded-xl opacity-30 shadow-[inset_0_0_20px_rgba(168,85,247,0.4)]"></div>
        </div>
      </Link>
    </div>
  );
}; 