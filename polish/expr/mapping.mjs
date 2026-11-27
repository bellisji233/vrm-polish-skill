// refresh the integration config's keys and mapping from the test workspace's expression keys
import {readFileSync, writeFileSync} from 'node:fs';
const [,, sessionFile, configFile, kit] = process.argv;
const {vrmExpressionMapping} = await import(kit + '/public/vrm-expression-map.mjs');
const st = JSON.parse(readFileSync(sessionFile, 'utf8')); const ks = st.keys || st.state?.keys;
const keys = Object.fromEntries(Object.entries(ks).map(([n, o]) => [n, Object.entries(o).map(([object, key]) => ({object, key}))]));
const c = JSON.parse(readFileSync(configFile, 'utf8')); c.keys = keys; c.mapping = vrmExpressionMapping(keys);
writeFileSync(configFile, JSON.stringify(c)); console.log('MAPPING', Object.keys(keys).length, c.mapping.length);
