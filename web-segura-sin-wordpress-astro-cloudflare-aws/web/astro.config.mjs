import { defineConfig } from 'astro/config';

// Web 100 % estática: HTML, CSS y JS en ficheros. Sin servidor, sin PHP, sin base de datos expuesta.
export default defineConfig({
  site: 'https://tudominio.es',
  output: 'static',
  build: {
    // CSS siempre en ficheros, nunca en línea: así la Content-Security-Policy puede prohibir estilos en línea.
    inlineStylesheets: 'never',
  },
  vite: {
    build: { assetsInlineLimit: 0 },
  },
});
