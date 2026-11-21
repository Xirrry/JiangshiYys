import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import skinColors from './skin-colors.js';
export default defineConfig({base:'./',plugins:[vue()],css:{postcss:{plugins:[skinColors()]}},build:{outDir:'dist',manifest:true,emptyOutDir:false}});
