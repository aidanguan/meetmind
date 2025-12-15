<script setup lang="ts">
import { ref, onMounted } from 'vue';
import api from '@/api';
import { useRouter } from 'vue-router';

interface Project {
  id: number;
  name: string;
  description: string;
  created_at: string;
}

const projects = ref<Project[]>([]);
const router = useRouter();
const dialogVisible = ref(false);
const form = ref({
  name: '',
  description: ''
});

const fetchProjects = async () => {
  try {
    const response = await api.get('/projects/');
    projects.value = response.data;
  } catch (error) {
    console.error(error);
  }
};

const createProject = async () => {
  try {
    await api.post('/projects/', form.value);
    dialogVisible.value = false;
    form.value = { name: '', description: '' };
    fetchProjects();
  } catch (error) {
    console.error(error);
  }
};

onMounted(fetchProjects);
</script>

<template>
  <div class="min-h-screen flex flex-col bg-background-light dark:bg-background-dark font-sans text-text-main dark:text-gray-100">
    <!-- Header -->
    <header class="flex items-center justify-between whitespace-nowrap border-b border-border-light dark:border-border-dark bg-background-light/80 dark:bg-surface-dark/90 backdrop-blur-md px-6 py-3 sticky top-0 z-50 transition-colors duration-300">
      <div class="flex items-center gap-3">
        <div class="size-9 text-primary dark:text-white flex items-center justify-center rounded-lg bg-primary/5 dark:bg-white/10">
          <span class="material-symbols-outlined text-[22px]">graphic_eq</span>
        </div>
        <h2 class="text-lg font-bold tracking-tight text-text-main dark:text-white">TranscribeWeb</h2>
      </div>
      <div class="flex items-center gap-3">
        <button class="flex items-center justify-center rounded-lg size-9 text-text-muted hover:text-text-main hover:bg-black/5 dark:text-gray-400 dark:hover:bg-white/10 transition-colors">
          <span class="material-symbols-outlined text-[22px]">settings</span>
        </button>
        <button class="flex items-center justify-center rounded-lg size-9 text-text-muted hover:text-text-main hover:bg-black/5 dark:text-gray-400 dark:hover:bg-white/10 transition-colors relative">
          <span class="material-symbols-outlined text-[22px]">notifications</span>
          <span class="absolute top-2 right-2.5 size-2 bg-red-600 rounded-full border-2 border-background-light dark:border-surface-dark"></span>
        </button>
        <div class="h-5 w-px bg-border-light dark:bg-gray-700 mx-1"></div>
        <div class="bg-center bg-no-repeat aspect-square bg-cover rounded-full size-9 cursor-pointer ring-1 ring-border-light dark:ring-gray-700 hover:ring-primary/30 transition-all" 
             data-alt="User profile avatar" 
             :style="{ backgroundImage: 'url(/images/avatar.jpg)' }">
        </div>
      </div>
    </header>

    <main class="flex-1 w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 flex flex-col gap-8">
      <div class="flex flex-col sm:flex-row sm:items-end justify-between gap-6">
        <div class="flex flex-col gap-2">
          <h1 class="text-3xl font-bold tracking-tight text-text-main dark:text-white">项目概览</h1>
          <p class="text-text-muted dark:text-gray-400 text-sm font-normal tracking-wide">管理您的会议录音与转写记录</p>
        </div>
        <button @click="dialogVisible = true" class="flex items-center justify-center gap-2 rounded-lg h-10 px-5 bg-primary hover:bg-primary-hover text-white text-sm font-medium shadow-soft transition-all transform active:scale-[0.98] w-full sm:w-auto">
          <span class="material-symbols-outlined text-[20px]">add</span>
          <span>新建项目</span>
        </button>
      </div>

      <div class="flex flex-col lg:flex-row gap-5 items-start lg:items-center justify-between">
        <div class="flex flex-wrap gap-2 overflow-x-auto pb-2 lg:pb-0 w-full lg:w-auto scrollbar-hide">
          <button class="flex h-8 items-center justify-center px-4 rounded-full bg-primary text-white text-xs font-medium transition-colors shadow-sm">
            全部
          </button>
          <button class="flex h-8 items-center justify-center px-4 rounded-full bg-white dark:bg-surface-dark text-text-muted dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-border-light dark:border-border-dark text-xs font-medium transition-colors">
            已完成
          </button>
          <button class="flex h-8 items-center justify-center px-4 rounded-full bg-white dark:bg-surface-dark text-text-muted dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-border-light dark:border-border-dark text-xs font-medium transition-colors">
            转写中
          </button>
          <button class="flex h-8 items-center justify-center px-4 rounded-full bg-white dark:bg-surface-dark text-text-muted dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-border-light dark:border-border-dark text-xs font-medium transition-colors">
            草稿
          </button>
        </div>
        <div class="w-full lg:max-w-xs">
          <div class="relative flex items-center w-full h-10 rounded-lg group">
            <div class="absolute left-3 text-gray-400 dark:text-gray-500 flex items-center pointer-events-none transition-colors group-focus-within:text-primary">
              <span class="material-symbols-outlined text-[20px]">search</span>
            </div>
            <input class="w-full h-9 rounded-lg border border-border-light dark:border-gray-700 bg-white dark:bg-surface-dark pl-10 pr-4 text-sm text-text-main dark:text-white placeholder:text-gray-400 focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 transition-all shadow-sm" placeholder="搜索项目..."/>
          </div>
        </div>
      </div>

      <div class="w-full bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-card overflow-hidden flex flex-col">
        <div class="hidden sm:flex items-center px-6 py-3 bg-background-light dark:bg-surface-dark/50 border-b border-border-light dark:border-border-dark text-xs font-semibold text-text-muted dark:text-gray-500">
          <div class="flex-1 pl-1">项目名称</div>
          <div class="w-40">创建日期</div>
          <div class="w-24 text-right pr-2">操作</div>
        </div>
        
        <div class="divide-y divide-border-light dark:divide-border-dark">
          <div v-if="projects.length === 0" class="px-6 py-8 text-center text-text-muted dark:text-gray-500 text-sm">
            暂无项目，请点击"新建项目"创建。
          </div>
          
          <div v-for="project in projects" :key="project.id" 
               class="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 px-6 py-4 hover:bg-background-light/50 dark:hover:bg-white/5 transition-colors group cursor-pointer"
               @click="router.push(`/project/${project.id}`)">
            <div class="flex items-center gap-4 flex-1 min-w-0">
              <div class="size-10 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 flex items-center justify-center shrink-0 border border-gray-200 dark:border-gray-700">
                <span class="material-symbols-outlined">description</span>
              </div>
              <div class="flex flex-col min-w-0 gap-0.5">
                <div class="flex items-center gap-2">
                  <h3 class="text-sm font-bold text-text-main dark:text-white truncate">{{ project.name }}</h3>
                  <!-- <span class="inline-flex items-center px-1.5 py-0.5 rounded-sm text-[10px] font-medium bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800/50">已完成</span> -->
                </div>
                <p class="text-xs text-text-muted dark:text-gray-500 truncate font-medium">{{ project.description || '无描述' }}</p>
              </div>
            </div>
            <div class="flex items-center justify-between sm:contents">
              <div class="text-sm text-text-muted dark:text-gray-400 w-auto sm:w-40 pl-[56px] sm:pl-0 font-medium">
                {{ new Date(project.created_at).toLocaleDateString() }}
              </div>
              <div class="w-auto sm:w-24 flex items-center justify-end gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                <button class="p-1.5 text-gray-400 hover:text-primary hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors" title="下载" @click.stop>
                  <span class="material-symbols-outlined text-[18px]">download</span>
                </button>
                <button class="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors" title="删除" @click.stop>
                  <span class="material-symbols-outlined text-[18px]">delete</span>
                </button>
                <button class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors" title="更多" @click.stop>
                  <span class="material-symbols-outlined text-[18px]">more_vert</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="px-6 py-4 bg-background-light/30 dark:bg-surface-dark border-t border-border-light dark:border-border-dark flex items-center justify-between">
          <p class="text-xs text-text-muted dark:text-gray-500 font-medium">显示 {{ projects.length }} 条记录</p>
          <div class="flex gap-2">
            <button class="px-3 py-1.5 rounded text-xs font-medium text-text-muted bg-white border border-border-light disabled:opacity-50 hover:bg-gray-50 dark:bg-surface-dark dark:border-border-dark dark:text-gray-400 dark:hover:bg-gray-700 transition-colors shadow-sm" disabled>
              上一页
            </button>
            <button class="px-3 py-1.5 rounded text-xs font-medium text-text-main bg-white border border-border-light hover:bg-gray-50 dark:bg-surface-dark dark:border-border-dark dark:text-white dark:hover:bg-gray-700 transition-colors shadow-sm">
              下一页
            </button>
          </div>
        </div>
      </div>
    </main>

    <el-dialog v-model="dialogVisible" title="Create New Project" width="30%">
      <el-form :model="form" label-position="top">
        <el-form-item label="Project Name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="createProject">Create</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>
