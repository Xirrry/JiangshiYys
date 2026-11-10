import assert from 'node:assert/strict';
import {reactive} from 'vue';
import {cloneJson} from './model.js';
const value=reactive({settings:{width:640,aspect:true},windows:{a:{x:-1920}},roles:['a']});
const copied=cloneJson(value);
assert.deepEqual(copied,{settings:{width:640,aspect:true},windows:{a:{x:-1920}},roles:['a']});
copied.windows.a.x=100;assert.equal(value.windows.a.x,-1920);
console.log('PASS: Vue reactive settings, per-role profiles and saved plans serialize without proxy clone errors.');
