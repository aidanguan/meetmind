<script setup lang="ts">
import { ref, onMounted, computed, nextTick, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '@/api';
import { ElMessage } from 'element-plus';
import MarkdownIt from 'markdown-it';

const route = useRoute();
const router = useRouter();
const recordingId = route.params.id;
const md = new MarkdownIt();

const recording = ref<any>(null);
const minutes = ref<any>(null);
const loading = ref(false);
const isGenerating = ref(false);
const streamContent = ref('');

// Editing states
const isEditingName = ref(false);
const editedName = ref('');
const isEditingDate = ref(false);
const editedDate = ref<Date | null>(null);

const isEditingMinutes = ref(false);
const editedMinutesContent = ref('');

// Audio Player states
const audioRef = ref<HTMLAudioElement | null>(null);
const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const playbackRate = ref(1);
const stopAt = ref<number | null>(null);

const renderedContent = computed(() => {
    return md.render(streamContent.value || minutes.value?.content || '');
});

const mediaSrc = computed(() => {
  if (!recording.value || !recording.value.media_url) return '';
  return `/api${recording.value.media_url}`;
});

const mediaType = computed(() => {
  if (!recording.value || !recording.value.media_url) return '';
  const url: string = recording.value.media_url.toLowerCase();
  if (url.endsWith('.m4a') || url.endsWith('.mp4')) return 'audio/mp4';
  if (url.endsWith('.wav')) return 'audio/wav';
  if (url.endsWith('.ogg')) return 'audio/ogg';
  return 'audio/mpeg';
});

const fetchRecording = async () => {
    try {
        const res = await api.get(`/recordings/${recordingId}`);
        recording.value = res.data;
    } catch (error) {
        console.error("Failed to fetch recording", error);
    }
};

const fetchMinutes = async () => {
  try {
    const res = await api.get(`/recordings/${recordingId}/minutes`);
    minutes.value = res.data;
    if (minutes.value?.content) {
        streamContent.value = minutes.value.content;
    }
  } catch (error) {
    minutes.value = null;
  }
};

const startStreaming = async () => {
    loading.value = true;
    isGenerating.value = true;
    streamContent.value = ''; 
    
    try {
        const response = await fetch(`/api/recordings/${recordingId}/minutes/stream?context=`);
        
        if (!response.ok) {
            throw new Error(response.statusText);
        }
        
        const reader = response.body?.getReader();
        if (!reader) throw new Error("No reader available");
        
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            streamContent.value += text;
        }
        
        await fetchMinutes();
        
    } catch (e) {
        ElMessage.error('Generation failed: ' + e);
        console.error(e);
    } finally {
        loading.value = false;
        isGenerating.value = false;
    }
};

// Helper for formatting time MM:SS
const formatTime = (ms: number) => {
    if (!ms && ms !== 0) return '00:00';
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

// Title Editing
const startEditingName = async () => {
    if (!recording.value) return;
    editedName.value = recording.value.filename;
    isEditingName.value = true;
    await nextTick();
    const input = document.getElementById('recording-name-input') as HTMLInputElement;
    if (input) {
        input.focus();
        input.select();
    }
};

const saveRecordingName = async () => {
    if (!recording.value || !editedName.value.trim()) {
        isEditingName.value = false;
        return;
    }
    
    if (editedName.value.trim() === recording.value.filename) {
        isEditingName.value = false;
        return;
    }

    try {
        await api.put(`/recordings/${recordingId}`, {
            filename: editedName.value.trim()
        });
        recording.value.filename = editedName.value.trim();
        isEditingName.value = false;
        ElMessage.success('Renamed successfully');
    } catch (e) {
        ElMessage.error('Failed to rename recording');
    }
};

// Date Editing
const startEditingDate = async () => {
    if (!recording.value) return;
    editedDate.value = recording.value.created_at ? new Date(recording.value.created_at) : new Date();
    isEditingDate.value = true;
};

const saveRecordingDate = async () => {
    if (!recording.value || !editedDate.value) {
        isEditingDate.value = false;
        return;
    }
    
    try {
        await api.put(`/recordings/${recordingId}`, {
            created_at: editedDate.value.toISOString()
        });
        recording.value.created_at = editedDate.value.toISOString();
        isEditingDate.value = false;
        ElMessage.success('Date updated successfully');
    } catch (e) {
        ElMessage.error('Failed to update date');
    }
};

// Minutes Editing
const startEditingMinutes = () => {
    editedMinutesContent.value = streamContent.value || minutes.value?.content || '';
    isEditingMinutes.value = true;
};

const cancelEditMinutes = () => {
    isEditingMinutes.value = false;
    editedMinutesContent.value = '';
};

const saveMinutes = async () => {
    try {
        await api.put(`/recordings/${recordingId}/minutes`, {
            content: editedMinutesContent.value
        });
        // Update local state
        if (minutes.value) {
            minutes.value.content = editedMinutesContent.value;
        } else {
            // Should verify if this case happens (minutes obj doesn't exist but we are editing?)
            // Usually fetchMinutes ensures minutes object exists or is null.
            // If null, we might need to handle creation, but we assume it exists if we are editing.
            await fetchMinutes();
        }
        streamContent.value = editedMinutesContent.value;
        isEditingMinutes.value = false;
        ElMessage.success('Minutes saved');
    } catch (e) {
        ElMessage.error('Failed to save minutes');
    }
};

// Audio Player Logic
const onTimeUpdate = () => {
  if (audioRef.value) {
    const now = audioRef.value.currentTime * 1000;
    currentTime.value = now; // Convert to ms

    if (stopAt.value && now >= stopAt.value) {
        audioRef.value.pause();
        isPlaying.value = false;
        stopAt.value = null;
    }
  }
};

const onLoadedMetadata = () => {
    if (audioRef.value) {
        duration.value = audioRef.value.duration * 1000;
    }
};

const onEnded = () => {
    isPlaying.value = false;
};

const togglePlay = () => {
    if (!audioRef.value) return;
    if (isPlaying.value) {
        audioRef.value.pause();
    } else {
        audioRef.value.play();
    }
    isPlaying.value = !isPlaying.value;
};

const seek = (seconds: number) => {
    if (!audioRef.value) return;
    stopAt.value = null;
    audioRef.value.currentTime = Math.max(0, Math.min(audioRef.value.duration, audioRef.value.currentTime + seconds));
};

const changeSpeed = () => {
    const rates = [0.5, 1.0, 1.25, 1.5, 2.0];
    const currentIndex = rates.indexOf(playbackRate.value);
    const nextRate = rates[(currentIndex + 1) % rates.length];
    playbackRate.value = nextRate;
    if (audioRef.value) {
        audioRef.value.playbackRate = nextRate;
    }
};

onMounted(async () => {
    await fetchRecording();
    await fetchMinutes();
    if (!minutes.value) {
        startStreaming();
    }
});
</script>

<template>
  <div class="h-screen flex flex-col bg-background-light dark:bg-background-dark font-sans text-text-main dark:text-gray-100 selection:bg-primary/10 selection:text-primary">
    <!-- Global Header -->
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

    <div class="flex-1 flex overflow-hidden max-w-7xl mx-auto w-full p-4 sm:p-6 lg:p-8 gap-6">
      
      <!-- Left Column: Minutes -->
      <div class="flex-1 flex flex-col bg-transparent overflow-hidden">
        
        <!-- Header Section (Breadcrumb + Title) -->
        <div class="mb-6">
            <!-- Breadcrumb -->
            <div class="flex items-center gap-2 text-sm text-text-muted dark:text-gray-500 mb-4">
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">首页</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push(`/project/${recording?.project_id}`)">项目详情</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="text-text-main dark:text-gray-300 font-medium truncate max-w-[200px]">会议纪要</span>
            </div>

            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div class="flex items-center gap-3 group">
                    <template v-if="!isEditingName">
                        <h1 class="text-2xl sm:text-3xl font-bold text-text-main dark:text-white tracking-tight truncate max-w-md">{{ recording?.filename || 'Untitled Recording' }}</h1>
                        <button class="text-text-muted hover:text-primary transition-colors" @click="startEditingName">
                            <span class="material-symbols-outlined text-[20px]">edit</span>
                        </button>
                    </template>
                    <template v-else>
                        <input 
                            id="recording-name-input"
                            v-model="editedName"
                            @keyup.enter="saveRecordingName"
                            @blur="saveRecordingName"
                            class="text-2xl sm:text-3xl font-bold text-text-main dark:text-white bg-transparent border-b border-primary focus:outline-none w-full max-w-md"
                        />
                    </template>
                     <span class="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-medium border border-green-200" v-if="minutes">Saved</span>
                </div>
                
                <div class="flex items-center gap-3">
                     <button class="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm" @click="fetchMinutes">
                        <span class="material-symbols-outlined text-[18px]">save</span>
                        Save Draft
                    </button>
                    <button class="flex items-center gap-2 px-3 py-1.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors shadow-sm">
                        <span class="material-symbols-outlined text-[18px]">ios_share</span>
                        Export
                    </button>
                </div>
            </div>
            
            <div class="flex items-center gap-6 text-sm font-medium text-text-muted dark:text-gray-500 mt-3">
                <span class="flex items-center gap-1.5 group cursor-pointer" @click="startEditingDate">
                    <span class="material-symbols-outlined text-[16px]">calendar_today</span>
                    <template v-if="!isEditingDate">
                         {{ recording?.created_at ? new Date(recording.created_at).toLocaleDateString() : 'N/A' }} 
                         {{ recording?.created_at ? new Date(recording.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '' }}
                         <span class="material-symbols-outlined text-[14px] opacity-0 group-hover:opacity-100 transition-opacity">edit</span>
                    </template>
                    <el-date-picker
                        v-else
                        v-model="editedDate"
                        type="datetime"
                        format="YYYY/MM/DD HH:mm"
                        size="small"
                        :teleported="false"
                        @change="saveRecordingDate"
                        @blur="isEditingDate = false"
                        style="width: 180px"
                        ref="datePickerRef"
                    />
                </span>
                <span class="flex items-center gap-1.5"><span class="material-symbols-outlined text-[16px]">schedule</span> {{ formatTime(duration) }}</span>
            </div>
        </div>

        <!-- Minutes Content Area -->
        <div class="flex-1 bg-surface-light dark:bg-surface-dark rounded-xl shadow-card border border-border-light dark:border-border-dark overflow-hidden flex flex-col">
            
            <!-- Toolbar -->
            <div class="px-6 py-4 border-b border-border-light dark:border-border-dark flex items-center justify-between bg-gray-50/50 dark:bg-surface-dark/50">
                <h3 class="text-xs font-bold text-text-muted uppercase tracking-wider">Meeting Minutes</h3>
                
                <div class="flex items-center gap-2">
                    <template v-if="isEditingMinutes">
                         <button @click="cancelEditMinutes" class="text-text-muted hover:text-text-main text-sm font-medium px-3 py-1 rounded transition-colors">
                            Cancel
                        </button>
                         <button @click="saveMinutes" class="text-white bg-primary hover:bg-primary-hover text-sm font-bold px-3 py-1 rounded transition-colors shadow-sm">
                            Save
                        </button>
                    </template>
                    <template v-else>
                        <button @click="startEditingMinutes" class="text-text-muted hover:text-primary text-sm font-medium flex items-center gap-1 px-3 py-1 rounded transition-colors hover:bg-gray-100 dark:hover:bg-gray-800" :disabled="isGenerating">
                            <span class="material-symbols-outlined text-[16px]">edit</span>
                            Edit
                        </button>
                        <div class="h-4 w-px bg-border-light dark:bg-border-dark mx-1"></div>
                        <button v-if="!isGenerating" @click="startStreaming" class="text-primary hover:text-primary-hover text-sm font-bold flex items-center gap-1 bg-primary/5 px-3 py-1 rounded-full transition-colors">
                            <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
                            AI Regenerate
                        </button>
                        <div v-else class="text-primary text-sm font-bold flex items-center gap-2 animate-pulse px-3 py-1">
                                <span class="w-2 h-2 rounded-full bg-primary"></span> Generating...
                        </div>
                    </template>
                </div>
            </div>

            <!-- Content Body -->
            <div class="flex-1 overflow-y-auto p-6 lg:p-8 relative">
                
                <textarea 
                    v-if="isEditingMinutes"
                    v-model="editedMinutesContent"
                    class="w-full h-full bg-transparent border-none resize-none focus:ring-0 text-text-main dark:text-gray-300 font-mono text-sm leading-relaxed"
                    placeholder="Enter meeting minutes..."
                ></textarea>

                <div v-else class="prose dark:prose-invert max-w-none prose-headings:font-bold prose-h1:text-2xl prose-h2:text-xl prose-p:text-text-main dark:prose-p:text-gray-300 prose-li:text-text-main dark:prose-li:text-gray-300 prose-blockquote:border-l-4 prose-blockquote:border-primary prose-blockquote:bg-gray-50 dark:prose-blockquote:bg-gray-800/50 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r" 
                     v-html="renderedContent">
                </div>
                
                 <div v-if="!streamContent && loading && !isEditingMinutes" class="absolute inset-0 flex flex-col items-center justify-center bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm z-10">
                    <span class="material-symbols-outlined text-4xl animate-spin mb-2 text-primary">progress_activity</span>
                    <span class="text-sm font-medium">AI is writing...</span>
                </div>
                
                <div v-if="!streamContent && !loading && !minutes && !isEditingMinutes" class="flex flex-col items-center justify-center h-full opacity-50">
                     <span class="material-symbols-outlined text-4xl mb-2">description</span>
                     <span class="text-sm font-medium">No minutes yet. Click 'AI Regenerate' to start.</span>
                </div>
            </div>
        </div>

      </div>

      <!-- Right Column: Sidebar -->
      <div class="w-[340px] flex flex-col gap-6 pt-0 shrink-0">
        
        <!-- Audio Player Card -->
        <div class="bg-surface-light dark:bg-surface-dark rounded-xl shadow-card border border-border-light dark:border-border-dark p-6">
            <div class="flex justify-between items-center mb-6">
                <span class="text-xs font-bold text-text-muted dark:text-gray-500 uppercase tracking-wider">录音回放</span>
                <div class="flex items-center gap-1.5 text-xs text-red-600 font-medium bg-red-50 dark:bg-red-900/20 px-2 py-1 rounded-full border border-red-100 dark:border-red-900/30">
                    <span class="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse"></span>
                    实时同步
                </div>
            </div>

            <!-- Waveform Visualization -->
            <div class="h-12 flex items-center justify-center gap-1 mb-6 px-2">
                 <div v-for="i in 30" :key="i" 
                    class="w-1.5 bg-primary rounded-full transition-all duration-300 ease-in-out"
                    :class="{'opacity-20': !isPlaying}"
                    :style="{ 
                        height: isPlaying ? `${30 + Math.random() * 70}%` : '30%',
                        opacity: isPlaying ? (Math.random() > 0.5 ? 1 : 0.6) : 0.2
                    }"></div>
            </div>

            <!-- Progress Bar -->
            <div class="relative w-full h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full mb-2 cursor-pointer group overflow-hidden" @click="(e) => {
                    const rect = (e.target as HTMLElement).getBoundingClientRect();
                    const percent = (e.clientX - rect.left) / rect.width;
                    stopAt = null;
                    if(audioRef) audioRef.currentTime = percent * audioRef.duration;
                }">
                <div class="absolute top-0 left-0 h-full bg-primary rounded-full transition-all duration-100" 
                    :style="{ width: `${(currentTime / duration) * 100}%` }"></div>
            </div>
            <div class="flex justify-between text-[11px] text-text-muted dark:text-gray-500 font-bold mb-6 font-mono tracking-wide">
                <span>{{ formatTime(currentTime) }}</span>
                <span>{{ formatTime(duration) }}</span>
            </div>

            <!-- Controls -->
            <div class="flex items-center justify-between px-2">
                <button @click="changeSpeed" class="text-xs font-bold text-text-muted hover:text-primary w-9 h-9 rounded-lg border border-border-light dark:border-border-dark hover:border-primary flex items-center justify-center transition-all bg-white dark:bg-surface-dark">
                    {{ playbackRate }}x
                </button>
                
                <div class="flex items-center gap-4">
                    <button @click="seek(-10)" class="text-text-muted hover:text-primary transition-colors p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800">
                        <span class="material-symbols-outlined text-[24px]">replay_10</span>
                    </button>
                    
                    <button @click="togglePlay" class="size-14 rounded-full bg-primary hover:bg-primary-hover flex items-center justify-center text-white shadow-soft transition-transform hover:scale-105 active:scale-95">
                        <span class="material-symbols-outlined text-[32px] ml-1" v-if="!isPlaying">play_arrow</span>
                        <span class="material-symbols-outlined text-[32px]" v-else>pause</span>
                    </button>
                    
                    <button @click="seek(10)" class="text-text-muted hover:text-primary transition-colors p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800">
                        <span class="material-symbols-outlined text-[24px]">forward_10</span>
                    </button>
                </div>

                <div class="w-9"></div> <!-- Spacer -->
            </div>

            <!-- Hidden Audio Element -->
            <audio ref="audioRef" class="hidden" @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMetadata" @ended="onEnded" v-if="recording && recording.media_url">
                <source :src="mediaSrc" :type="mediaType">
            </audio>
        </div>

      </div>

    </div>
  </div>
</template>

<style>
/* Markdown Styles override */
.prose ul {
    list-style-type: disc;
    padding-left: 1.5em;
}
.prose ol {
    list-style-type: decimal;
    padding-left: 1.5em;
}
.prose h1, .prose h2, .prose h3 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}
.prose p {
    margin-bottom: 1em;
    line-height: 1.6;
}
</style>