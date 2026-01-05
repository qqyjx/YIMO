#!/usr/bin/env node
/**
 * Mermaid SVG 生成脚本
 *
 * 使用方法:
 *   1. 安装依赖: npm install @mermaid-js/mermaid-cli
 *   2. 运行: node scripts/generate-diagram.js
 *
 * 或者直接使用 npx:
 *   npx @mermaid-js/mermaid-cli -i figures/plan/roadmap.mmd -o figures/plan/roadmap.svg -b white
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const INPUT = path.join(ROOT, 'figures', 'plan', 'roadmap.mmd');
const OUTPUT = path.join(ROOT, 'figures', 'plan', 'roadmap.svg');

// Mermaid 配置
const CONFIG = {
    theme: 'default',
    themeVariables: {
        fontFamily: 'Microsoft YaHei, SimHei, PingFang SC, sans-serif'
    },
    flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: 'basis'
    }
};

const configPath = path.join(ROOT, 'mermaid-config.json');
fs.writeFileSync(configPath, JSON.stringify(CONFIG, null, 2));

console.log('正在生成 SVG...');

try {
    execSync(`npx -y @mermaid-js/mermaid-cli mmdc \
        -i "${INPUT}" \
        -o "${OUTPUT}" \
        -c "${configPath}" \
        -b white \
        --scale 2`, {
        stdio: 'inherit',
        cwd: ROOT
    });

    console.log(`\n✅ SVG 已生成: ${OUTPUT}`);

    // 清理配置文件
    fs.unlinkSync(configPath);
} catch (error) {
    console.error('生成失败:', error.message);
    console.log('\n💡 替代方案:');
    console.log('   1. 用浏览器打开 figures/plan/roadmap.html');
    console.log('   2. 点击"导出 SVG"按钮');
    process.exit(1);
}
