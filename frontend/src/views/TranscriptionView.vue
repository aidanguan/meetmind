<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '@/api';
import { ElMessage } from 'element-plus';
import { Loading, Search, Edit, Share, Download, User, VideoPlay, VideoPause, RefreshLeft, RefreshRight, CopyDocument, Microphone, Connection, Calendar, Timer, UserFilled } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const recordingId = route.params.id;

const transcript = ref<any>(null);
const currentTime = ref(0);
const duration = ref(0);
const isPlaying = ref(false);
const playbackRate = ref(1);
const volume = ref(1);
const audioRef = ref<HTMLAudioElement | null>(null);
const recording = ref<any>(null);
const pollInterval = ref<any>(null);
const statusInterval = ref<any>(null);
const errorState = ref<string>('');
const searchQuery = ref('');
const editingSpeaker = ref<{ id: string, name: string } | null>(null);
const speakerColors = ref<Record<string, string>>({});
const stopAt = ref<number | null>(null);
const isEditingName = ref(false);
const editedName = ref('');
const isEditingDate = ref(false);
const editedDate = ref<Date | null>(null);

const mediaSrc = computed(() => {
  if (!recording.value || !recording.value.media_url) return '';
  return `/api${recording.value.media_url}`;
});

const mediaType = computed(() => {
  if (!recording.value || !recording.value.media_url) return '';
  const url: string = recording.value.media_url.toLowerCase();
  if (url.endsWith('.m4a')) return 'audio/mp4';
  if (url.endsWith('.mp4')) return 'video/mp4';
  if (url.endsWith('.wav')) return 'audio/wav';
  if (url.endsWith('.ogg')) return 'audio/ogg';
  return 'audio/mpeg';
});

const isVideo = computed(() => {
    return mediaType.value.startsWith('video/');
});

// Helper for formatting time MM:SS
const formatTime = (ms: number) => {
    if (!ms && ms !== 0) return '00:00';
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

const generateColor = (speakerId: string) => {
    const colors = ['bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-red-500', 'bg-orange-500', 'bg-teal-500', 'bg-cyan-500'];
    let hash = 0;
    for (let i = 0; i < speakerId.length; i++) {
        hash = speakerId.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % colors.length;
    return colors[index];
};

// Generate avatar color/initials based on speaker ID hash
const getAvatarColor = (speakerId: string) => {
    if (!speakerColors.value[speakerId]) {
        speakerColors.value[speakerId] = generateColor(speakerId);
    }
    return speakerColors.value[speakerId];
};

const getInitials = (speakerId: string) => {
    const name = speakerId.replace('Speaker ', '');
    return name.substring(0, 2).toUpperCase();
};

const fetchRecording = async () => {
  try {
    const res = await api.get(`/recordings/${recordingId}`);
    recording.value = res.data;
    if (recording.value.status === 'error') {
      errorState.value = recording.value.error_message || 'Transcription failed. Please try again.';
      if (pollInterval.value) {
        clearInterval(pollInterval.value);
        pollInterval.value = null;
      }
    } else {
      errorState.value = '';
    }
  } catch (e) {
    recording.value = null;
  }
};

const fetchTranscript = async () => {
  try {
    const res = await api.get(`/recordings/${recordingId}/transcript`);
    transcript.value = res.data;
    if (pollInterval.value) {
        clearInterval(pollInterval.value);
        pollInterval.value = null;
    }
  } catch (error: any) {
    if (error.response) {
      if (error.response.status === 404) {
        const detail = error.response.data?.detail || '';
        if (detail && detail.toLowerCase().includes('failed')) {
          errorState.value = detail;
          if (pollInterval.value) {
            clearInterval(pollInterval.value);
            pollInterval.value = null;
          }
          return;
        }
        if (!pollInterval.value) {
          pollInterval.value = setInterval(fetchTranscript, 3000);
        }
      } else {
        errorState.value = 'Unexpected error fetching transcript.';
      }
    } else {
      console.error(error);
    }
  }
};

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

const seekTo = (ms: number, endMs?: number) => {
  const element = audioRef.value;
  if (element) {
    const startMs = Number(ms);
    if (isNaN(startMs)) return;

    // Helper to perform the seek and play
    const doSeekAndPlay = () => {
        // Always seek
        const timeInSeconds = startMs / 1000;
        
        // Ensure valid time
        if (timeInSeconds >= 0 && timeInSeconds <= element.duration) {
             element.currentTime = timeInSeconds;
        } else {
             console.warn("Invalid seek time:", timeInSeconds, "Duration:", element.duration);
             if (element.duration && timeInSeconds > element.duration) {
                 element.currentTime = element.duration;
             } else {
                 element.currentTime = 0;
             }
        }
        
        // Set stop point
        if (endMs) {
            stopAt.value = Number(endMs);
        } else {
            stopAt.value = null;
        }

        // Ensure we play
        element.play().then(() => {
            isPlaying.value = true;
        }).catch(e => {
            console.error("Playback failed:", e);
        });
    };

    // If metadata is loaded, we can seek immediately
    if (element.readyState >= 1) { // HAVE_METADATA
        doSeekAndPlay();
    } else {
        // Wait for metadata to load
        const onLoaded = () => {
            doSeekAndPlay();
            element.removeEventListener('loadedmetadata', onLoaded);
        };
        element.addEventListener('loadedmetadata', onLoaded);
        // Force load if needed
        element.load();
    }
  }
};

const generateMinutes = () => {
    router.push(`/recording/${recordingId}/minutes?generate=true`);
};

const copyTranscript = () => {
    if (!transcript.value) return;
    navigator.clipboard.writeText(transcript.value.plain_text).then(() => {
        ElMessage.success('Transcript copied to clipboard');
    });
};

const filteredTranscript = computed(() => {
    if (!transcript.value || !transcript.value.content) return [];
    if (!searchQuery.value) return transcript.value.content;
    const query = searchQuery.value.toLowerCase();
    return transcript.value.content.filter((seg: any) => 
        seg.text.toLowerCase().includes(query) || 
        seg.speaker_id.toLowerCase().includes(query)
    );
});

const speakerStats = computed(() => {
    if (!transcript.value || !transcript.value.content) return [];
    const stats: Record<string, number> = {};
    let totalDuration = 0;
    
    transcript.value.content.forEach((seg: any) => {
        const dur = seg.end - seg.start;
        stats[seg.speaker_id] = (stats[seg.speaker_id] || 0) + dur;
        totalDuration += dur;
    });
    
    return Object.entries(stats).map(([speaker, dur]) => ({
        speaker,
        percentage: Math.round((dur / totalDuration) * 100)
    })).sort((a, b) => b.percentage - a.percentage);
});

const activeSegmentIndex = computed(() => {
    if (!transcript.value) return -1;
    return transcript.value.content.findIndex((seg: any) => 
        currentTime.value >= seg.start && currentTime.value <= seg.end
    );
});

onMounted(() => {
  fetchRecording();
  fetchTranscript();
  statusInterval.value = setInterval(fetchRecording, 3000);
});

onUnmounted(() => {
  if (pollInterval.value) {
    clearInterval(pollInterval.value);
  }
  if (statusInterval.value) {
    clearInterval(statusInterval.value);
  }
});

const retryTranscribe = async () => {
  try {
    await api.post(`/recordings/${recordingId}/transcribe`);
    errorState.value = '';
    transcript.value = null;
    if (pollInterval.value) {
      clearInterval(pollInterval.value);
    }
    pollInterval.value = setInterval(fetchTranscript, 3000);
  } catch (e) {
    errorState.value = 'Retry failed. Please check settings.';
  }
};

const startEditingSpeaker = async (speakerId: string, index: number) => {
    editingSpeaker.value = { id: speakerId, name: speakerId };
    await nextTick();
    // Use index to target the specific input element
    const input = document.querySelector(`input[data-index="${index}"]`) as HTMLInputElement;
    if (input) {
        input.focus();
        input.select();
    }
};

const saveSpeakerName = async () => {
    if (!editingSpeaker.value || !transcript.value) return;
    
    const originalId = editingSpeaker.value.id;
    const newName = editingSpeaker.value.name.trim();
    
    if (!newName || newName === originalId) {
        editingSpeaker.value = null;
        return;
    }

    // Preserve color mapping for the new name
    if (!speakerColors.value[newName] && speakerColors.value[originalId]) {
        speakerColors.value[newName] = speakerColors.value[originalId];
    }

    try {
        // Optimistic update
        transcript.value.content.forEach((seg: any) => {
            if (seg.speaker_id === originalId) {
                seg.speaker_id = newName;
            }
        });

        editingSpeaker.value = null;
        
        await api.put(`/recordings/${recordingId}/speakers`, {
            original_speaker_id: originalId,
            new_speaker_id: newName
        });
        
        ElMessage.success(`Renamed ${originalId} to ${newName}`);
    } catch (e) {
        ElMessage.error('Failed to update speaker name');
        // Revert (simplified: just fetch again)
        fetchTranscript();
    }
};

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

const handleExport = (format: string) => {
    window.open(`/api/recordings/${recordingId}/transcript/export?format=${format}`, '_blank');
};
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
      
      <!-- Left Column: Transcript -->
      <div class="flex-1 flex flex-col bg-transparent overflow-hidden">
        
        <!-- Transcript Header -->
        <div class="mb-6">
            <!-- Breadcrumb -->
            <div class="flex items-center gap-2 text-sm text-text-muted dark:text-gray-500 mb-4">
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">首页</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push(`/project/${recording?.project_id}`)">项目详情</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="text-text-main dark:text-gray-300 font-medium truncate max-w-[200px]">{{ recording?.filename || 'Untitled' }}</span>
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
                </div>
                <div class="flex items-center gap-3">
                    <button @click="retryTranscribe" class="flex items-center justify-center w-9 h-9 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-text-main dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm" title="重新转写">
                        <span class="material-symbols-outlined text-[18px]">refresh</span>
                    </button>
                    <button @click="copyTranscript" class="flex items-center justify-center w-9 h-9 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-lg text-text-main dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm" title="复制文本">
                        <span class="material-symbols-outlined text-[18px]">content_copy</span>
                    </button>
                    <button class="flex items-center gap-2 h-9 px-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-lg transition-all shadow-md hover:shadow-lg active:scale-[0.98] text-sm font-bold border border-transparent" @click="generateMinutes">
                        <span class="material-symbols-outlined text-[18px] text-white">auto_awesome</span>
                        生成纪要
                    </button>
                    
                    <el-dropdown trigger="click" @command="handleExport">
                        <span class="el-dropdown-link">
                            <button class="flex items-center justify-center w-9 h-9 bg-primary hover:bg-primary-hover text-white rounded-lg transition-all shadow-soft active:scale-[0.98]" title="导出结果">
                                <span class="material-symbols-outlined text-[18px]">download</span>
                            </button>
                        </span>
                        <template #dropdown>
                            <el-dropdown-menu>
                                <el-dropdown-item command="docx">导出 Word (.docx)</el-dropdown-item>
                                <el-dropdown-item command="pdf">导出 PDF (.pdf)</el-dropdown-item>
                            </el-dropdown-menu>
                        </template>
                    </el-dropdown>
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
                <span class="flex items-center gap-1.5"><span class="material-symbols-outlined text-[16px]">group</span> {{ speakerStats.length }} 位参会者</span>
            </div>
        </div>

        <!-- Transcript List Container -->
        <div class="flex-1 overflow-y-auto pr-2 relative space-y-0.5 scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-700">
             <div v-if="errorState" class="absolute inset-0 flex flex-col items-center justify-center">
                <p class="text-red-600 mb-4">{{ errorState }}</p>
                <button class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700" @click="retryTranscribe">Retry Transcribe</button>
            </div>

            <div v-else-if="!transcript" class="absolute inset-0 flex flex-col items-center justify-center">
                <span class="material-symbols-outlined text-4xl text-primary animate-spin mb-4">progress_activity</span>
                <p class="text-text-muted dark:text-gray-500">Transcribing... Please wait.</p>
            </div>

            <template v-else>
                <div v-for="(segment, index) in filteredTranscript" :key="index"
                    class="flex gap-3 p-2 rounded-lg transition-all cursor-pointer border border-transparent group relative"
                    :class="[
                        activeSegmentIndex === index ? 'bg-primary/5 border-primary/20 shadow-sm' : 'hover:bg-white/60 dark:hover:bg-surface-dark/40'
                    ]"
                    @click="seekTo(segment.start, segment.end)">
                    
                    <!-- Active Indicator -->
                    <div class="absolute left-0 top-2 bottom-2 w-1 rounded-r-full transition-opacity duration-200"
                        :class="[
                            activeSegmentIndex === index ? 'bg-primary opacity-100' : getAvatarColor(segment.speaker_id).replace('bg-', 'bg-').concat(' opacity-0 group-hover:opacity-100')
                        ]">
                    </div>

                    <!-- Avatar -->
                    <div class="flex-shrink-0 pt-0.5">
                        <div class="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-[10px] shadow-sm ring-2 ring-white dark:ring-gray-700"
                            :class="getAvatarColor(segment.speaker_id)">
                            {{ getInitials(segment.speaker_id) }}
                        </div>
                    </div>

                    <!-- Content -->
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-0.5">
                            <div v-if="editingSpeaker && editingSpeaker.id === segment.speaker_id" @click.stop class="flex items-center gap-2">
                                <input 
                                    v-model="editingSpeaker.name"
                                    :data-index="index"
                                    @keyup.enter="saveSpeakerName"
                                    @blur="saveSpeakerName"
                                    class="text-xs font-bold text-text-main dark:text-gray-100 border-b border-primary focus:outline-none bg-transparent px-1 py-0.5 min-w-[80px]"
                                    @click.stop
                                />
                            </div>
                            <div v-else class="flex items-center gap-2 group/speaker cursor-pointer" @click.stop="startEditingSpeaker(segment.speaker_id, index)">
                                <span class="font-bold text-text-main dark:text-gray-100 text-xs hover:text-primary transition-colors">{{ segment.speaker_id }}</span>
                                <span class="material-symbols-outlined text-[12px] text-gray-400 opacity-0 group-hover/speaker:opacity-100 transition-opacity">edit</span>
                            </div>

                            <span class="text-[10px] text-gray-400 font-mono tracking-wide bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">{{ formatTime(segment.start) }}</span>
                            <span v-if="activeSegmentIndex === index" 
                                class="text-[10px] font-bold px-2 py-0.5 bg-primary/10 text-primary rounded-full flex items-center gap-1">
                                播放中
                            </span>
                        </div>
                        <p class="text-text-main dark:text-gray-300 leading-snug text-[14px]"
                           :class="{'font-medium': activeSegmentIndex === index}">
                            {{ segment.text }}
                        </p>
                    </div>
                </div>
            </template>
        </div>
      </div>

      <!-- Right Column: Sidebar -->
      <div class="w-[340px] flex flex-col gap-6 pt-2 shrink-0">
        
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

            <!-- Hidden Audio/Video Element -->
            <video ref="audioRef" class="hidden" @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMetadata" @ended="onEnded" v-if="recording && recording.media_url && isVideo" preload="auto">
                <source :src="mediaSrc" :type="mediaType">
            </video>
            <audio ref="audioRef" class="hidden" @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMetadata" @ended="onEnded" v-else-if="recording && recording.media_url" preload="auto">
                <source :src="mediaSrc" :type="mediaType">
            </audio>
        </div>

        <!-- Speakers Card -->
        <div class="bg-surface-light dark:bg-surface-dark rounded-xl shadow-card border border-border-light dark:border-border-dark p-6">
             <h3 class="text-sm font-bold text-text-main dark:text-white mb-5">发言人</h3>
             <div class="space-y-5">
                <div v-for="stat in speakerStats" :key="stat.speaker" class="flex items-center gap-4">
                    <div class="w-9 h-9 rounded-full flex items-center justify-center text-white text-xs font-bold ring-2 ring-white dark:ring-gray-700 shadow-sm"
                         :class="getAvatarColor(stat.speaker)">
                        {{ getInitials(stat.speaker) }}
                    </div>
                    <div class="flex-1">
                        <div class="flex justify-between text-sm mb-1.5">
                            <span class="font-bold text-text-main dark:text-gray-200">{{ stat.speaker }}</span>
                            <span class="text-text-muted dark:text-gray-500 text-xs font-medium">{{ stat.percentage }}%</span>
                        </div>
                        <div class="h-1.5 w-full bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div class="h-full rounded-full transition-all duration-500" 
                                :class="getAvatarColor(stat.speaker).replace('bg-', 'bg-opacity-80 bg-')"
                                :style="{ width: `${stat.percentage}%` }"></div>
                        </div>
                    </div>
                </div>
             </div>
        </div>

        <!-- Action Buttons (Moved to Header) -->
        <!-- <div class="grid grid-cols-2 gap-4">
            <button @click="copyTranscript" class="flex items-center justify-center gap-2 bg-surface-light dark:bg-surface-dark border border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-700 text-text-main dark:text-gray-200 font-bold py-3 px-4 rounded-xl shadow-sm transition-all hover:shadow text-sm">
                <span class="material-symbols-outlined text-[20px]">content_copy</span>
                复制文本
            </button>
        </div> -->

      </div>

    </div>
  </div>
</template>
