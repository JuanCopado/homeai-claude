import { mkdir, copyFile, cp } from 'node:fs/promises';
await mkdir('dist',{recursive:true});
for(const file of ['index.html','app.js','styles.css','studio.css','studio-pro.css','studio-pro.js','catalog-v16.js','catalog-v16.css','design-v16.css','advisor-v16.js','advisor-v16.css','photo-studio.js','catalog-enhancements.js','alternatives.js','planner-geometry.js','room-planner.js','room-planner.css','material-library.js','material-library.css','workspace-v17.js','workspace-v17.css','ai-orchestrator.js','ai-orchestrator.css','ai-interior-preview.js','ai-interior-preview.css','sw.js','manifest.webmanifest','icon.svg']) await copyFile(file,'dist/'+file);
await cp('assets','dist/assets',{recursive:true});
console.log('HomeAI static build complete');
