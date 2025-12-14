<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '@/api';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();
const projectId = route.params.id;

interface Recording {
  id: number;
  filename: string;
  status: string;
  duration: number;
  created_at: string;
}

const recordings = ref<Recording[]>([]);
const project = ref<any>({});

const fetchProject = async () => {
  try {
    const res = await api.get(`/projects/${projectId}`);
    project.value = res.data;
  } catch (error) {
    console.error(error);
  }
};

const fetchRecordings = async () => {
  try {
    const res = await api.get(`/recordings/project/${projectId}`);
    recordings.value = res.data;
  } catch (error) {
    console.error(error);
  }
};

const handleUploadSuccess = () => {
  ElMessage.success('上传成功');
  fetchRecordings();
};

const startTranscribe = async (id: number) => {
  try {
    await api.post(`/recordings/${id}/transcribe`);
    ElMessage.success('开始转录');
    // Navigate immediately to transcription page
    router.push(`/recording/${id}`);
  } catch (error) {
    console.error(error);
  }
};

const viewTranscript = (id: number) => {
  router.push(`/recording/${id}`);
};

const viewMinutes = (id: number) => {
  router.push(`/recording/${id}/minutes`);
};

const formatDuration = (seconds: number) => {
  if (!seconds) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const getStatusConfig = (status: string) => {
  switch (status) {
    case 'completed':
      return { text: '已完成', class: 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50', icon: 'check_circle' };
    case 'transcribing':
      return { text: '处理中', class: 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800/50', icon: 'progress_activity' };
    case 'pending':
      return { text: '待处理', class: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600', icon: 'hourglass_empty' };
    case 'failed':
      return { text: '失败', class: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800/50', icon: 'error' };
    default:
      return { text: status, class: 'bg-gray-100 text-gray-600', icon: 'help' };
  }
};

onMounted(() => {
  fetchProject();
  fetchRecordings();
});
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <!-- Header (Consistent with Home) -->
    <header class="flex items-center justify-between whitespace-nowrap border-b border-border-light dark:border-border-dark bg-background-light/80 dark:bg-surface-dark/90 backdrop-blur-md px-6 py-3 sticky top-0 z-50 transition-colors duration-300">
      <div class="flex items-center gap-3 cursor-pointer" @click="router.push('/')">
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
      <!-- Breadcrumb & Header -->
      <div class="flex flex-col gap-6">
        <div class="flex items-center gap-2 text-sm text-text-muted dark:text-gray-500">
          <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">首页</span>
          <span class="material-symbols-outlined text-[14px]">chevron_right</span>
          <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">项目列表</span>
          <span class="material-symbols-outlined text-[14px]">chevron_right</span>
          <span class="text-text-main dark:text-gray-300 font-medium">{{ project.name }}</span>
        </div>
        
        <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div class="flex flex-col gap-2">
            <h1 class="text-3xl font-bold tracking-tight text-text-main dark:text-white">{{ project.name }}</h1>
            <p class="text-text-muted dark:text-gray-400 text-sm font-normal tracking-wide">
              项目创建于 {{ new Date(project.created_at).toLocaleDateString() }} • 包含 {{ recordings.length }} 个文件
            </p>
          </div>
          <button class="flex items-center justify-center gap-2 rounded-lg h-9 px-4 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm">
            <span class="material-symbols-outlined text-[18px]">edit</span>
            <span>编辑详情</span>
          </button>
        </div>
      </div>

      <!-- Upload Area -->
      <div class="w-full">
        <el-upload
          class="w-full"
          drag
          :action="`/api/recordings/upload/${projectId}`"
          :on-success="handleUploadSuccess"
          :show-file-list="false"
          multiple
        >
          <div class="w-full h-32 border-2 border-dashed border-border-light dark:border-border-dark rounded-xl bg-surface-light dark:bg-surface-dark flex flex-col items-center justify-center gap-3 transition-colors hover:border-primary/50 group cursor-pointer">
            <div class="size-12 rounded-full bg-primary/5 dark:bg-primary/20 text-primary flex items-center justify-center group-hover:scale-110 transition-transform">
              <span class="material-symbols-outlined text-[24px]">cloud_upload</span>
            </div>
            <div class="text-center">
              <p class="text-base font-bold text-text-main dark:text-white">上传录音文件</p>
              <p class="text-sm text-text-muted dark:text-gray-500 mt-1">拖放文件至此，或点击浏览 (支持 MP3, WAV, M4A)</p>
            </div>
          </div>
        </el-upload>
      </div>

      <!-- File List Section -->
      <div class="flex flex-col gap-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-bold text-text-main dark:text-white">项目文件</h2>
          <div class="flex items-center gap-2">
            <button class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-text-muted dark:text-gray-400 transition-colors">
              <span class="material-symbols-outlined text-[20px]">filter_list</span>
            </button>
            <button class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-text-muted dark:text-gray-400 transition-colors">
              <span class="material-symbols-outlined text-[20px]">grid_view</span>
            </button>
          </div>
        </div>

        <div class="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-card overflow-hidden flex flex-col">
          <!-- Table Header -->
          <div class="hidden sm:grid grid-cols-12 gap-4 px-6 py-3 bg-background-light dark:bg-surface-dark/50 border-b border-border-light dark:border-border-dark text-xs font-semibold text-text-muted dark:text-gray-500">
            <div class="col-span-6 pl-1">文件名称</div>
            <div class="col-span-1">上传日期</div>
            <div class="col-span-1">时长</div>
            <div class="col-span-1 text-center">状态</div>
            <div class="col-span-3 text-right pr-2">操作</div>
          </div>

          <!-- Table Body -->
          <div class="divide-y divide-border-light dark:divide-border-dark">
            <div v-if="recordings.length === 0" class="px-6 py-12 text-center flex flex-col items-center gap-3">
              <div class="size-12 rounded-full bg-gray-50 dark:bg-gray-800 flex items-center justify-center">
                 <span class="material-symbols-outlined text-gray-300 text-[24px]">folder_open</span>
              </div>
              <p class="text-text-muted dark:text-gray-500 text-sm">暂无文件，请上传录音开始。</p>
            </div>

            <div v-for="recording in recordings" :key="recording.id" class="flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 px-6 py-4 hover:bg-background-light/50 dark:hover:bg-white/5 transition-colors group items-center">
              <!-- Name -->
              <div class="col-span-6 flex items-center gap-4 w-full min-w-0">
                <div class="size-10 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 flex items-center justify-center shrink-0 border border-gray-200 dark:border-gray-700">
                  <span class="material-symbols-outlined">mic</span>
                </div>
                <div class="flex flex-col min-w-0 gap-0.5">
                  <h3 class="text-sm font-bold text-text-main dark:text-white truncate">{{ recording.filename }}</h3>
                  <p class="text-xs text-text-muted dark:text-gray-500 truncate font-medium">{{ (recording.duration / 1024 / 1024).toFixed(1) }} MB</p> <!-- Mock size if not available -->
                </div>
              </div>

              <!-- Date -->
              <div class="col-span-1 text-sm text-text-muted dark:text-gray-400 font-medium pl-[56px] sm:pl-0 whitespace-nowrap">
                {{ new Date(recording.created_at).toLocaleDateString() }}
              </div>

              <!-- Duration -->
              <div class="col-span-1 text-sm text-text-muted dark:text-gray-400 font-medium pl-[56px] sm:pl-0">
                {{ formatDuration(recording.duration) }}
              </div>

              <!-- Status -->
              <div class="col-span-1 flex justify-start sm:justify-center pl-[56px] sm:pl-0">
                <span :class="['inline-flex items-center justify-center size-7 rounded-full border', getStatusConfig(recording.status).class]" :title="getStatusConfig(recording.status).text">
                   <span class="material-symbols-outlined text-[18px]" :class="{'animate-spin': recording.status === 'transcribing'}">
                     {{ getStatusConfig(recording.status).icon }}
                   </span>
                </span>
              </div>

              <!-- Actions -->
              <div class="col-span-3 flex items-center justify-end gap-2 w-full sm:w-auto mt-2 sm:mt-0 pl-[56px] sm:pl-0">
                <template v-if="recording.status === 'pending'">
                  <button @click="startTranscribe(recording.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-primary hover:bg-primary-hover text-white text-xs font-medium transition-colors shadow-sm">
                    <span class="material-symbols-outlined text-[14px]">play_arrow</span>
                    转录
                  </button>
                  <button class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors">
                    <span class="material-symbols-outlined text-[18px]">more_vert</span>
                  </button>
                </template>

                <template v-else-if="recording.status === 'transcribing'">
                  <button class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium transition-colors shadow-sm">
                    取消
                  </button>
                  <button class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors">
                    <span class="material-symbols-outlined text-[18px]">more_vert</span>
                  </button>
                </template>

                <template v-else-if="recording.status === 'completed'">
                  <div class="flex items-center gap-2">
                    <button @click="viewTranscript(recording.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium transition-colors shadow-sm whitespace-nowrap">
                      <span class="material-symbols-outlined text-[14px]">visibility</span>
                      转录
                    </button>
                    <button @click="viewMinutes(recording.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-primary/5 hover:bg-primary/10 border border-primary/20 text-primary dark:text-primary-light text-xs font-medium transition-colors shadow-sm whitespace-nowrap">
                      <span class="material-symbols-outlined text-[14px]">description</span>
                      纪要
                    </button>
                    <button class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors">
                      <span class="material-symbols-outlined text-[18px]">more_vert</span>
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div class="px-6 py-4 bg-background-light/30 dark:bg-surface-dark border-t border-border-light dark:border-border-dark flex items-center justify-between">
            <p class="text-xs text-text-muted dark:text-gray-500 font-medium">显示 1-{{ recordings.length }} 共 {{ recordings.length }} 个文件</p>
            <div class="flex gap-2">
              <button class="size-8 flex items-center justify-center rounded text-text-muted bg-white border border-border-light disabled:opacity-50 hover:bg-gray-50 dark:bg-surface-dark dark:border-border-dark dark:text-gray-400 dark:hover:bg-gray-700 transition-colors shadow-sm" disabled>
                <span class="material-symbols-outlined text-[16px]">chevron_left</span>
              </button>
              <button class="size-8 flex items-center justify-center rounded text-text-main bg-white border border-border-light hover:bg-gray-50 dark:bg-surface-dark dark:border-border-dark dark:text-white dark:hover:bg-gray-700 transition-colors shadow-sm">
                <span class="material-symbols-outlined text-[16px]">chevron_right</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* Override element-plus upload styles to match tailwind custom design */
:deep(.el-upload) {
  width: 100%;
  display: block;
}
:deep(.el-upload-dragger) {
  width: 100%;
  height: auto;
  padding: 0;
  border: none;
  background-color: transparent;
  border-radius: 0.75rem; /* xl */
}
:deep(.el-upload-dragger:hover) {
  border: none;
}
:deep(.el-upload-dragger.is-dragover) {
  background-color: transparent; /* Handle with tailwind group-hover */
}
</style>
