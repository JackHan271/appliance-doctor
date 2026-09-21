/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // 带蓝的深色文字，不用纯黑
        ink: '#1A3A5C',
        'ink-soft': '#5B7A94',
        // 淡蓝基底 + 品牌蓝
        mist: '#EAF2F8',
        panel: '#FFFFFF',
        brand: {
          DEFAULT: '#2E7DB8',
          deep: '#1E5A86',
          soft: '#F5F9FC',
        },
        line: '#D8E6F0',
        // 三级安全功能色
        safe: {
          green: '#2E9E5B',
          'green-bg': '#E7F5EC',
          yellow: '#C9911C',
          'yellow-bg': '#FBF3E1',
          red: '#D64545',
          'red-bg': '#FBEAEA',
        },
      },
      borderRadius: {
        card: '14px',
      },
    },
  },
  plugins: [],
}
