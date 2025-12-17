<script setup lang="ts">
import { ref, onMounted, computed, nextTick, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import api from '@/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import MarkdownIt from 'markdown-it';
import mermaid from 'mermaid';
import AppSidebar from '@/components/AppSidebar.vue';

const route = useRoute();
const router = useRouter();
const projectId = route.params.id;

// Interfaces
interface Recording {
  id: number;
  filename: string;
  status: string;
  duration: number;
  created_at: string;
  minutes_id?: number | null;
}

interface ProjectDocument {
  id: number;
  filename: string;
  file_type: string;
  created_at: string;
  gemini_file_uri?: string;
}

interface KnowledgeBase {
  id: number;
  content: Record<string, string>; // { prd: "...", timeline: "..." }
  updated_at: string;
}

// State
const recordings = ref<Recording[]>([]);
const documents = ref<ProjectDocument[]>([]);
const project = ref<any>({});
const activeTab = ref<'files' | 'kb' | 'settings' | 'chat'>('files');
const knowledgeBase = ref<KnowledgeBase | null>(null);
const activeKbSection = ref('prd');
const isGeneratingKB = ref(false);
const isUploading = ref(false);

// File List State
const fileTypeFilter = ref<string>('all');
const uploadType = ref<string>('recording');

const uploadAccept = computed(() => {
    if (uploadType.value === 'recording') return 'audio/*,video/*';
    return '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt';
});

const uploadAction = computed(() => {
    if (uploadType.value === 'recording') return `/api/recordings/upload/${projectId}`;
    return `/api/projects/${projectId}/documents`;
});

const uploadData = computed(() => {
    if (uploadType.value === 'recording') return {};
    return { file_type: uploadType.value };
});

const allFiles = computed(() => {
  let files: any[] = [];
  
  // Map recordings
  recordings.value.forEach(r => {
    files.push({
      ...r,
      type: 'recording',
      displayType: 'Meeting Recording',
      category: 'recording'
    });
  });

  // Map documents
  documents.value.forEach(d => {
    files.push({
      ...d,
      type: 'document',
      displayType: d.file_type.toUpperCase(),
      category: d.file_type
    });
  });

  // Filter
  if (fileTypeFilter.value !== 'all') {
    if (fileTypeFilter.value === 'recording') {
      files = files.filter(f => f.type === 'recording');
    } else {
      files = files.filter(f => f.category === fileTypeFilter.value);
    }
  }

  // Sort by date desc
  return files.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
});

// Chat State
interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  thoughts?: string[];
  actions?: { tool: string; query: string }[];
  isStreaming?: boolean;
}

interface ChatSession {
  id: number;
  title: string;
  created_at: string;
}

const chatSessions = ref<ChatSession[]>([]);
const currentSessionId = ref<number | null>(null);
const chatMessages = ref<ChatMessage[]>([]);
const chatInput = ref('');
const isChatting = ref(false);
const chatContainer = ref<HTMLElement | null>(null);

// Modal State
const showSelectMinutesModal = ref(false);
const selectedMinutesIds = ref<number[]>([]);
const selectedDocumentIds = ref<number[]>([]);

// Hotwords State
interface Hotword {
    text: string;
    weight: number;
    lang: string;
}

const hotwords = ref<Hotword[]>([]);
const isSavingSettings = ref(false);

watch(() => project.value, (newVal) => {
    if (newVal && newVal.hotwords) {
        hotwords.value = JSON.parse(JSON.stringify(newVal.hotwords)); // Deep copy
    } else {
        hotwords.value = [];
    }
}, { immediate: true });

const addHotword = () => {
    hotwords.value.push({ text: '', weight: 4, lang: 'zh' });
};

const removeHotword = (index: number) => {
    hotwords.value.splice(index, 1);
};

const saveSettings = async () => {
    isSavingSettings.value = true;
    try {
        await api.patch(`/projects/${projectId}/hotwords`, {
            hotwords: hotwords.value
        });
        ElMessage.success('设置已保存');
        fetchProject(); // Refresh
    } catch (error) {
        console.error(error);
        ElMessage.error('保存失败');
    } finally {
        isSavingSettings.value = false;
    }
};

// Markdown Setup
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
});

// Chat Helpers
const handleMessageClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  const link = target.closest('.source-link') as HTMLElement;
  
  if (link) {
      e.preventDefault();
      const type = link.dataset.type;
      const id = link.dataset.id;
      const section = link.dataset.section;

      if (type === 'minutes' && id) {
          router.push(`/recording/${id}/minutes`);
      } else if (type === 'transcript' && id) {
          router.push(`/recording/${id}`);
      } else if (type === 'kb') {
          activeTab.value = 'kb';
          if (section) activeKbSection.value = section;
      } else if (type === 'document') {
          activeTab.value = 'files';
          fileTypeFilter.value = 'all'; // Reset filter to show all files
          // Ideally we would highlight the file, but for now just navigating is good.
          ElMessage.info('已跳转到文件列表');
      }
  }
};

const transformCitations = (html: string) => {
  // Replace [[Source]] with a styled interactive link
  return html.replace(/\[\[(.*?)\]\]/g, (match, sourceName) => {
    let icon = 'description';
    let type = '';
    let id = '';
    let section = '';
    let displayName = sourceName;
    let isCitation = false;
    let href = '#';

    // Parse sourceName
    // Formats: 
    // Minutes_Filename_ID
    // Transcript_Filename_ID
    // Document_Filename_ID
    // PRD_ProjectID, SPECS_ProjectID, etc.
    
    if (sourceName.toLowerCase().includes('minutes')) {
        icon = 'event_note';
        const match = sourceName.match(/^Minutes_(.*)_(\d+)$/i);
        if (match) {
            displayName = match[1];
            id = match[2];
            type = 'minutes';
            href = `/recording/${id}/minutes`;
            isCitation = true;
        }
    } else if (sourceName.toLowerCase().includes('transcript')) {
        icon = 'record_voice_over';
        const match = sourceName.match(/^Transcript_(.*)_(\d+)$/i);
        if (match) {
            displayName = match[1];
            id = match[2];
            type = 'transcript';
            href = `/recording/${id}`;
            isCitation = true;
        }
    } else if (sourceName.match(/^(PRD|SPECS|TIMELINE|GLOSSARY|BUSINESS)_(\d+)$/i)) {
        icon = 'library_books';
        const match = sourceName.match(/^(PRD|SPECS|TIMELINE|GLOSSARY|BUSINESS)_(\d+)$/i);
        if (match) {
            const key = match[1].toLowerCase();
            if (key === 'prd') section = 'prd';
            else if (key === 'specs') section = 'specs';
            else if (key === 'timeline') section = 'timeline';
            else if (key === 'glossary') section = 'glossary';
            else if (key === 'business') section = 'business_flows';
            
            displayName = {
                'prd': '需求文档',
                'specs': '功能说明书',
                'timeline': '时间表',
                'glossary': '术语表',
                'business_flows': '业务流程'
            }[section] || section;
            
            type = 'kb';
            href = `/project/${projectId}?tab=kb`;
            isCitation = true;
        }
    } else if (sourceName.toLowerCase().startsWith('document_')) {
        icon = 'article';
        const match = sourceName.match(/^Document_(.*)_(\d+)$/i);
        if (match) {
            displayName = match[1];
            id = match[2];
            type = 'document';
            href = `/project/${projectId}?tab=files`;
            isCitation = true;
        }
    }
    
    if (isCitation) {
        // Styled as a clickable link
        return `<a href="${href}" class="source-link inline-flex items-center gap-1 px-1.5 py-0.5 mx-1 rounded bg-primary/10 hover:bg-primary/20 text-primary text-xs font-medium cursor-pointer transition-colors align-middle no-underline select-none" 
            data-type="${type}" 
            data-id="${id}" 
            data-section="${section}"
            title="查看来源: ${displayName}">
            <span class="material-symbols-outlined text-[12px]">${icon}</span>
            <span class="max-w-[150px] truncate">${displayName}</span>
            <span class="material-symbols-outlined text-[10px]">open_in_new</span>
        </a>`;
    } else {
        // Fallback for unrecognized format
        return `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 mx-1 rounded bg-primary/10 text-primary text-xs font-medium align-middle cursor-default select-none">
          <span class="material-symbols-outlined text-[12px]">${icon}</span>
          <span>${sourceName}</span>
        </span>`;
    }
  });
};

const renderMessage = (content: string) => {
  if (!content) return '';
  const html = md.render(content);
  return transformCitations(html);
};

// Custom fence rule for mermaid
const defaultFence = md.renderer.rules.fence || function(tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.fence = function (tokens, idx, options, env, self) {
  const token = tokens[idx];
  const info = token.info ? token.info.trim() : '';
  if (info === 'mermaid') {
    return `<div class="mermaid">${token.content}</div>`;
  }
  return defaultFence(tokens, idx, options, env, self);
};

// Computed
const availableMinutes = computed(() => {
  return recordings.value.filter(r => r.minutes_id);
});

const renderedKbContent = computed(() => {
  if (!knowledgeBase.value || !knowledgeBase.value.content) return '';
  const content = knowledgeBase.value.content[activeKbSection.value] || '*No content for this section.*';
  const html = md.render(content);
  return transformCitations(html);
});

const isUserInteracting = ref(false);

// Watchers
watch(renderedKbContent, async () => {
  await nextTick();
  try {
    await mermaid.run({
      querySelector: '.mermaid'
    });
  } catch (e) {
    console.error('Mermaid render error:', e);
  }
});

watch(activeKbSection, () => {
    isUserInteracting.value = true;
});

// Watch chat messages to render mermaid diagrams
watch(chatMessages, async () => {
  await nextTick();
  try {
    await mermaid.run({
      querySelector: '.mermaid'
    });
  } catch (e) {
    // console.error('Mermaid render error:', e);
  }
}, { deep: true });

// Sync activeTab with route query
watch(
  () => route.query.tab,
  (newTab) => {
    if (newTab === 'kb') {
      activeTab.value = 'kb';
    } else if (newTab === 'settings') {
      activeTab.value = 'settings';
    } else if (newTab === 'chat') {
      activeTab.value = 'chat';
    } else {
      activeTab.value = 'files';
    }
  },
  { immediate: true }
);

// Actions
const scrollToBottom = async () => {
  await nextTick();
  if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
  }
};

// Chat Actions
const fetchChatSessions = async () => {
    try {
        const res = await api.get(`/projects/${projectId}/chat/sessions`);
        chatSessions.value = res.data;
    } catch (error) {
        console.error('Failed to fetch sessions', error);
    }
};

const createNewSession = async () => {
    try {
        const res = await api.post(`/projects/${projectId}/chat/sessions`);
        chatSessions.value.unshift(res.data);
        currentSessionId.value = res.data.id;
        chatMessages.value = []; // Clear current messages
    } catch (error) {
        console.error('Failed to create session', error);
    }
};

const loadSessionMessages = async (sessionId: number) => {
    // Prevent reloading if already on the same session (optional, but good for UX)
    if (currentSessionId.value === sessionId && chatMessages.value.length > 0) return;

    try {
        currentSessionId.value = sessionId;
        const res = await api.get(`/projects/chat/sessions/${sessionId}/messages`);
        
        // Map backend messages to frontend format
        chatMessages.value = res.data.map((msg: any) => ({
            id: msg.id,
            role: msg.role,
            content: msg.content,
            thoughts: msg.thought_process,
            isStreaming: false
        }));
        scrollToBottom();
    } catch (error) {
        console.error('Failed to load messages', error);
    }
};

const sendChatMessage = async () => {
  if (!chatInput.value.trim() || isChatting.value) return;
  
  // Create session if none exists
  if (!currentSessionId.value) {
      await createNewSession();
  }

  const userQuery = chatInput.value.trim();
  chatMessages.value.push({ role: 'user', content: userQuery });
  chatInput.value = '';
  
  const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      thoughts: [],
      actions: [],
      isStreaming: true
  };
  chatMessages.value.push(assistantMsg);
  isChatting.value = true;
  scrollToBottom();

  try {
      const response = await fetch(`${api.defaults.baseURL}/projects/${projectId}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
              query: userQuery,
              session_id: currentSessionId.value
          })
      });

      if (!response.ok) throw new Error('Chat request failed');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No reader');

      while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n\n');

          for (const line of lines) {
              if (line.startsWith('event:')) {
                  const lineParts = line.split('\n');
                  const eventLine = lineParts[0];
                  // Join the rest as data line, in case data contains newlines (though usually it's single line JSON)
                  const dataLine = lineParts.slice(1).join('\n'); 
                  
                  if (eventLine && dataLine) {
                      const event = eventLine.replace('event: ', '').trim();
                      const dataStr = dataLine.replace('data: ', '');

                      try {
                          const data = JSON.parse(dataStr);
                          
                          if (event === 'thought') {
                              if (!assistantMsg.thoughts) assistantMsg.thoughts = [];
                              assistantMsg.thoughts.push(data.content);
                          } else if (event === 'action') {
                              if (!assistantMsg.actions) assistantMsg.actions = [];
                              assistantMsg.actions.push({ tool: data.tool, query: data.query });
                          } else if (event === 'answer') {
                              // Append content for streaming effect
                              // Note: backend sends chunks, so we should append, not replace?
                              // Actually backend implementation: full_answer += chunk; yield chunk
                              // So data.content is just the chunk.
                              assistantMsg.content += data.content; 
                          } else if (event === 'session_id') {
                              // If backend created a session implicitly (fallback), update our ID
                              // But we create explicit session first now, so this is just a sync
                              if (!currentSessionId.value) currentSessionId.value = data.id;
                              fetchChatSessions(); // Refresh list to update titles
                          } else if (event === 'error') {
                              assistantMsg.content += `\n\n*Error: ${data.content}*`;
                          }
                          scrollToBottom();
                      } catch (e) {
                          console.error('Parse error', e);
                      }
                  }
              }
          }
      }
      fetchChatSessions(); // Update session list titles after chat
  } catch (error) {
      console.error(error);
      assistantMsg.content += '\n\n*Failed to get response.*';
  } finally {
      isChatting.value = false;
      assistantMsg.isStreaming = false;
      scrollToBottom();
  }
};

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

const fetchDocuments = async () => {
  try {
    const res = await api.get(`/projects/${projectId}/documents`);
    documents.value = res.data;
  } catch (error) {
    console.error(error);
  }
};

const fetchKnowledgeBase = async () => {
  try {
    const res = await api.get(`/projects/${projectId}/knowledge-base`);
    if (res.data && res.data.content) {
      knowledgeBase.value = res.data;
    }
  } catch (error) {
    console.error(error);
  }
};

const handleBeforeUpload = () => {
  isUploading.value = true;
  return true;
};

const handleUploadSuccess = () => {
  isUploading.value = false;
  ElMessage.success('上传成功');
  fetchRecordings();
  fetchDocuments();
};

const handleUploadError = () => {
  isUploading.value = false;
  ElMessage.error('上传失败');
};

const startTranscribe = async (id: number) => {
  try {
    await api.post(`/recordings/${id}/transcribe`);
    ElMessage.success('开始转录');
    fetchRecordings(); // Refresh status
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

const confirmDelete = async (file: any) => {
  try {
    await ElMessageBox.confirm(
      '确定要删除这个文件吗？此操作不可恢复。',
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      }
    );
    
    if (file.type === 'recording') {
        await api.delete(`/recordings/${file.id}`);
        fetchRecordings();
    } else {
        await api.delete(`/projects/${projectId}/documents/${file.id}`);
        fetchDocuments();
    }

    ElMessage.success('删除成功');
  } catch (error) {
    if (error !== 'cancel') {
        console.error(error);
        ElMessage.error('删除失败');
    }
  }
};

const showResearchModal = ref(false);
const researchStatusMessage = ref('');

const openGenerateModal = () => {
  // Pre-select all by default
  selectedMinutesIds.value = availableMinutes.value.map(r => r.minutes_id!);
  selectedDocumentIds.value = documents.value.map(d => d.id);
  showSelectMinutesModal.value = true;
};

const confirmGenerate = async () => {
  if (selectedMinutesIds.value.length === 0 && selectedDocumentIds.value.length === 0) {
    ElMessage.warning('请至少选择一个参考文件');
    return;
  }
  
  isGeneratingKB.value = true;
  showSelectMinutesModal.value = false;
  showResearchModal.value = true;
  researchStatusMessage.value = "Starting Deep Research Agent...";
  
  // Initialize knowledge base structure if null
  if (!knowledgeBase.value) {
      knowledgeBase.value = {
          id: 0,
          content: { prd: '', specs: '', business_flows: '', timeline: '', glossary: '' },
          updated_at: new Date().toISOString()
      };
  }

  try {
    const response = await fetch(`${api.defaults.baseURL}/projects/${projectId}/knowledge-base/generate/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            minutes_ids: selectedMinutesIds.value,
            document_ids: selectedDocumentIds.value
        })
    });

    if (!response.ok) throw new Error('Generation failed');
    if (!response.body) throw new Error('No response body');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
            if (line.startsWith('event: ')) {
                const [eventLine, ...dataLines] = line.split('\n');
                const event = eventLine.replace('event: ', '').trim();
                const dataStr = dataLines.join('\n').replace('data: ', '').trim();
                
                if (dataStr) {
                    if (event === 'status') {
                        try {
                            const data = JSON.parse(dataStr);
                            researchStatusMessage.value = data.message;
                        } catch (e) { console.error(e); }
                    } else if (event === 'done') {
                        try {
                            const data = JSON.parse(dataStr);
                            if (knowledgeBase.value && data.content) {
                                knowledgeBase.value.content = data.content;
                            }
                            isGeneratingKB.value = false;
                            showResearchModal.value = false;
                            ElMessage.success('知识库生成完成！');
                        } catch (e) { console.error(e); }
                    } else if (event === 'error') {
                        try {
                           const data = JSON.parse(dataStr);
                           ElMessage.error(`生成出错: ${data.message}`);
                        } catch(e) {
                           ElMessage.error(`生成出错: ${dataStr}`);
                        }
                        isGeneratingKB.value = false;
                        showResearchModal.value = false;
                    }
                }
            }
        }
    }

  } catch (error) {
    console.error(error);
    ElMessage.error('生成失败');
    isGeneratingKB.value = false;
    showResearchModal.value = false;
  }
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
  fetchDocuments();
  fetchKnowledgeBase();
  fetchChatSessions();
  mermaid.initialize({ startOnLoad: false, theme: 'default' });
});
</script>

<template>
  <div class="min-h-screen flex bg-background-light dark:bg-background-dark font-sans text-text-main dark:text-gray-100">
    <!-- Sidebar -->
    <AppSidebar :project-id="projectId" :project-name="project.name" :default-collapsed="true" />

    <!-- Main Content -->
    <main class="flex-1 flex flex-col h-screen overflow-hidden">
        <!-- Top Header (Simplified) -->
        <header class="h-16 flex items-center justify-between px-6 border-b border-border-light dark:border-border-dark bg-background-light/80 dark:bg-surface-dark/90 backdrop-blur-md">
            <div class="flex items-center gap-2 text-sm text-text-muted dark:text-gray-500">
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">首页</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="hover:text-primary cursor-pointer transition-colors" @click="router.push('/')">项目列表</span>
                <span class="material-symbols-outlined text-[14px]">chevron_right</span>
                <span class="text-text-main dark:text-gray-300 font-medium">{{ project.name }}</span>
            </div>

            <div class="flex items-center gap-3">
                 <button class="flex items-center justify-center rounded-lg size-9 text-text-muted hover:text-text-main hover:bg-black/5 dark:text-gray-400 dark:hover:bg-white/10 transition-colors">
                  <span class="material-symbols-outlined text-[22px]">settings</span>
                </button>
            </div>
        </header>

        <!-- Content Scroll Area -->
        <div class="flex-1 flex flex-col lg:p-6" :class="activeTab === 'chat' ? 'overflow-hidden p-2 pb-0' : 'overflow-y-auto p-4'">
            <div class="max-w-[1920px] mx-auto flex flex-col gap-8 w-full px-4 lg:px-8" :class="activeTab === 'chat' ? 'h-full' : ''">
                
                <!-- Header Info -->
                <div v-if="activeTab !== 'chat'" class="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div class="flex flex-col gap-2">
                    <h1 class="text-3xl font-bold tracking-tight text-text-main dark:text-white">{{ project.name }}</h1>
                    <p class="text-text-muted dark:text-gray-400 text-sm font-normal tracking-wide">
                      项目创建于 {{ new Date(project.created_at).toLocaleDateString() }} • 包含 {{ recordings.length }} 个文件
                    </p>
                  </div>
                  <button 
                    v-if="activeTab === 'kb'"
                    @click="openGenerateModal"
                    class="flex items-center justify-center gap-2 rounded-lg h-9 px-4 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
                  >
                    <span class="material-symbols-outlined text-[18px]">refresh</span>
                    <span>重新生成</span>
                  </button>
                  <!-- <button class="flex items-center justify-center gap-2 rounded-lg h-9 px-4 bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-200 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm">
                    <span class="material-symbols-outlined text-[18px]">edit</span>
                    <span>编辑详情</span>
                  </button> -->
                </div>

                <!-- FILES VIEW -->
                <div v-show="activeTab === 'files'" class="flex flex-col gap-8 animate-in fade-in duration-300">
                    <!-- File List Section -->
                    <div class="flex flex-col gap-4">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-4">
                            <h2 class="text-lg font-bold text-text-main dark:text-white">文件列表</h2>
                            <select v-model="fileTypeFilter" class="px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark bg-surface-light dark:bg-surface-dark text-sm text-text-main dark:text-gray-300 focus:ring-1 focus:ring-primary outline-none">
                                <option value="all">所有类型</option>
                                <option value="recording">会议录音</option>
                                <option value="rfp">需求文档 (RFP)</option>
                                <option value="design">设计方案</option>
                                <option value="test_plan">测试方案</option>
                                <option value="manual">操作手册</option>
                                <option value="other">其他文件</option>
                            </select>
                        </div>

                        <div class="flex items-center bg-teal-600 rounded-lg hover:bg-teal-700 transition-colors shadow-sm overflow-hidden">
                            <div class="relative border-r border-white/20">
                                <select v-model="uploadType" class="appearance-none bg-transparent text-white text-sm font-medium pl-3 pr-8 py-2 outline-none cursor-pointer">
                                    <option value="recording" class="text-gray-800">录音</option>
                                    <option value="rfp" class="text-gray-800">RFP</option>
                                    <option value="design" class="text-gray-800">设计</option>
                                    <option value="test_plan" class="text-gray-800">测试</option>
                                    <option value="manual" class="text-gray-800">手册</option>
                                    <option value="other" class="text-gray-800">其他</option>
                                </select>
                                <span class="material-symbols-outlined text-white text-[16px] absolute right-1 top-1/2 -translate-y-1/2 pointer-events-none">arrow_drop_down</span>
                            </div>
                            <el-upload
                              class="flex"
                              :action="uploadAction"
                              :data="uploadData"
                              :accept="uploadAccept"
                              :before-upload="handleBeforeUpload"
                              :on-success="handleUploadSuccess"
                              :on-error="handleUploadError"
                              :show-file-list="false"
                              multiple
                              :disabled="isUploading"
                            >
                              <button class="flex items-center gap-2 px-4 py-2 text-white text-sm font-medium disabled:opacity-70 disabled:cursor-not-allowed" :disabled="isUploading">
                                  <span v-if="isUploading" class="material-symbols-outlined text-[20px] animate-spin">progress_activity</span>
                                  <span v-else class="material-symbols-outlined text-[20px]">cloud_upload</span>
                                  {{ isUploading ? '上传中...' : '上传' }}
                              </button>
                            </el-upload>
                        </div>
                      </div>

                      <div class="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-card overflow-hidden flex flex-col">
                        <!-- Table Header -->
                        <div class="hidden sm:grid grid-cols-12 gap-4 px-6 py-3 bg-background-light dark:bg-surface-dark/50 border-b border-border-light dark:border-border-dark text-xs font-semibold text-text-muted dark:text-gray-500">
                          <div class="col-span-5 pl-1">文件名称</div>
                          <div class="col-span-2">类型</div>
                          <div class="col-span-2">上传日期</div>
                          <div class="col-span-1 text-center">状态</div>
                          <div class="col-span-2 text-right pr-2">操作</div>
                        </div>

                        <!-- Table Body -->
                        <div class="divide-y divide-border-light dark:divide-border-dark">
                          <div v-if="allFiles.length === 0" class="px-6 py-12 text-center flex flex-col items-center gap-3">
                            <div class="size-12 rounded-full bg-gray-50 dark:bg-gray-800 flex items-center justify-center">
                               <span class="material-symbols-outlined text-gray-300 text-[24px]">folder_open</span>
                            </div>
                            <p class="text-text-muted dark:text-gray-500 text-sm">暂无文件，请上传文件开始。</p>
                          </div>

                          <div v-for="file in allFiles" :key="file.type + file.id" class="flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 px-6 py-4 hover:bg-background-light/50 dark:hover:bg-white/5 transition-colors group items-center">
                            <!-- Name -->
                            <div class="col-span-5 flex items-center gap-4 w-full min-w-0">
                              <div class="size-10 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 flex items-center justify-center shrink-0 border border-gray-200 dark:border-gray-700">
                                <span class="material-symbols-outlined">{{ file.type === 'recording' ? 'mic' : 'description' }}</span>
                              </div>
                              <div class="flex flex-col min-w-0 gap-0.5">
                                <h3 class="text-sm font-bold text-text-main dark:text-white truncate">{{ file.filename }}</h3>
                                <p v-if="file.type === 'recording'" class="text-xs text-text-muted dark:text-gray-500 truncate font-medium">{{ (file.duration / 60).toFixed(1) }} min</p>
                                <p v-else class="text-xs text-text-muted dark:text-gray-500 truncate font-medium">Document</p>
                              </div>
                            </div>

                            <!-- Type -->
                            <div class="col-span-2">
                                <span class="inline-flex px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-400 font-medium">
                                    {{ file.displayType }}
                                </span>
                            </div>

                            <!-- Date -->
                            <div class="col-span-2 text-sm text-text-muted dark:text-gray-400 font-medium pl-[56px] sm:pl-0 whitespace-nowrap">
                              {{ new Date(file.created_at).toLocaleDateString() }}
                            </div>

                            <!-- Status -->
                            <div class="col-span-1 flex justify-start sm:justify-center pl-[56px] sm:pl-0">
                              <template v-if="file.type === 'recording'">
                                  <span :class="['inline-flex items-center justify-center size-7 rounded-full border', getStatusConfig(file.status).class]" :title="getStatusConfig(file.status).text">
                                     <span class="material-symbols-outlined text-[18px]" :class="{'animate-spin': file.status === 'transcribing'}">
                                       {{ getStatusConfig(file.status).icon }}
                                     </span>
                                  </span>
                              </template>
                              <template v-else>
                                  <span class="inline-flex items-center justify-center size-7 rounded-full border bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50" title="已上传">
                                     <span class="material-symbols-outlined text-[18px]">check_circle</span>
                                  </span>
                              </template>
                            </div>

                            <!-- Actions -->
                            <div class="col-span-2 flex items-center justify-end gap-2 w-full sm:w-auto mt-2 sm:mt-0 pl-[56px] sm:pl-0">
                              <template v-if="file.type === 'recording'">
                                  <template v-if="file.status === 'pending'">
                                    <button @click="startTranscribe(file.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-primary hover:bg-primary-hover text-white text-xs font-medium transition-colors shadow-sm">
                                      <span class="material-symbols-outlined text-[14px]">play_arrow</span>
                                      转录
                                    </button>
                                  </template>
                                  <template v-else-if="file.status === 'transcribing'">
                                    <div class="flex items-center gap-2">
                                      <button @click="viewTranscript(file.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium transition-colors shadow-sm whitespace-nowrap">
                                        <span class="material-symbols-outlined text-[14px]">visibility</span>
                                        查看进度
                                      </button>
                                    </div>
                                  </template>
                                  <template v-else-if="file.status === 'completed'">
                                    <div class="flex items-center gap-2">
                                      <button @click="viewTranscript(file.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-white dark:bg-surface-dark border border-border-light dark:border-border-dark text-text-main dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium transition-colors shadow-sm whitespace-nowrap">
                                        <span class="material-symbols-outlined text-[14px]">visibility</span>
                                        转录
                                      </button>
                                      <button @click="viewMinutes(file.id)" class="flex items-center justify-center gap-1 h-8 px-3 rounded bg-primary/5 hover:bg-primary/10 border border-primary/20 text-primary dark:text-primary-light text-xs font-medium transition-colors shadow-sm whitespace-nowrap">
                                        <span class="material-symbols-outlined text-[14px]">description</span>
                                        纪要
                                      </button>
                                    </div>
                                  </template>
                              </template>
                              <template v-else>
                                  <!-- Document Actions: View? (Maybe just download link if needed, but for now just delete) -->
                                  <!-- Could add a "View" button that opens media url -->
                              </template>

                              <!-- Delete Action for all statuses -->
                              <el-dropdown trigger="click" placement="bottom-end">
                                <button class="p-1.5 ml-1 text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors">
                                  <span class="material-symbols-outlined text-[18px]">more_vert</span>
                                </button>
                                <template #dropdown>
                                  <el-dropdown-menu>
                                    <el-dropdown-item @click="confirmDelete(file)" class="text-red-500">
                                      <div class="flex items-center gap-2 text-red-600">
                                        <span class="material-symbols-outlined text-[16px]">delete</span>
                                        删除
                                      </div>
                                    </el-dropdown-item>
                                  </el-dropdown-menu>
                                </template>
                              </el-dropdown>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                </div>

                <!-- KNOWLEDGE BASE VIEW -->
                <div v-show="activeTab === 'kb'" class="flex flex-col gap-6 animate-in fade-in duration-300">
                     <!-- Loading / Empty State -->
                     <div v-if="isGeneratingKB" class="flex flex-col items-center justify-center py-20 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark">
                        <span class="material-symbols-outlined text-5xl text-primary animate-spin mb-4">smart_toy</span>
                        <h3 class="text-lg font-bold">AI 正在构建项目知识库...</h3>
                        <p class="text-text-muted mt-2">正在分析会议纪要、生成 PRD、梳理时间表。</p>
                        <p class="text-text-muted text-sm mt-1">这可能需要几分钟时间，请耐心等待。</p>
                     </div>

                     <div v-else-if="!knowledgeBase" class="flex flex-col items-center justify-center py-20 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark text-center px-4">
                        <div class="size-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
                            <span class="material-symbols-outlined text-4xl text-primary">library_books</span>
                        </div>
                        <h2 class="text-2xl font-bold text-text-main dark:text-white mb-3">暂无项目知识库</h2>
                        <p class="text-text-muted max-w-md mx-auto mb-8">
                            AI 可以根据您的会议纪要自动生成项目需求文档 (PRD)、功能说明书、项目时间表和术语表。
                        </p>
                        <button @click="openGenerateModal" class="flex items-center gap-2 px-6 py-3 bg-primary hover:bg-primary-hover text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-primary/30">
                            <span class="material-symbols-outlined">auto_awesome</span>
                            开始生成知识库
                        </button>
                     </div>

                     <!-- KB Content Layout -->
                     <div v-else class="flex flex-col lg:flex-row gap-6 items-start">
                        <!-- Sidebar Navigation -->
                        <div class="w-full lg:w-64 shrink-0 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-2 flex flex-col gap-1 sticky top-0">
                            <button 
                                v-for="item in [
                                    { id: 'prd', label: '需求文档 (PRD)', icon: 'description' },
                                    { id: 'specs', label: '功能说明书', icon: 'settings_suggest' },
                                    { id: 'business_flows', label: '业务流程', icon: 'account_tree' },
                                    { id: 'timeline', label: '项目时间表', icon: 'calendar_month' },
                                    { id: 'glossary', label: '术语表', icon: 'menu_book' }
                                ]"
                                :key="item.id"
                                @click="activeKbSection = item.id"
                                class="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors text-left"
                                :class="activeKbSection === item.id ? 'bg-primary text-white shadow-md' : 'text-text-main dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                            >
                                <span class="material-symbols-outlined text-[20px]">{{ item.icon }}</span>
                                {{ item.label }}
                            </button>
                            
                            <!-- <div class="h-px bg-border-light dark:bg-border-dark my-2 mx-2"></div>
                            
                            <button @click="openGenerateModal" class="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-primary hover:bg-primary/5 transition-colors text-left">
                                <span class="material-symbols-outlined text-[20px]">refresh</span>
                                重新生成
                            </button> -->
                        </div>

                        <!-- Content Area -->
                        <div class="flex-1 min-w-0 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-8 shadow-sm">
                            <div class="prose dark:prose-invert max-w-none prose-headings:font-bold prose-a:text-primary" v-html="renderedKbContent"></div>
                        </div>
                     </div>
                </div>
                
                <!-- SETTINGS VIEW -->
                <div v-show="activeTab === 'settings'" class="flex flex-col gap-8 animate-in fade-in duration-300">
                    <div class="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-8 shadow-sm">
                        <div class="flex items-center justify-between mb-6">
                            <h2 class="text-xl font-bold text-text-main dark:text-white">项目设置</h2>
                            <button @click="saveSettings" :disabled="isSavingSettings" class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-white text-sm font-medium transition-colors shadow-sm disabled:opacity-50">
                                <span v-if="isSavingSettings" class="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
                                <span v-else class="material-symbols-outlined text-[18px]">save</span>
                                保存设置
                            </button>
                        </div>

                        <!-- Hotwords Section -->
                        <div class="flex flex-col gap-4">
                            <div class="flex items-center justify-between">
                                <div>
                                    <h3 class="text-base font-bold text-text-main dark:text-white">专业术语表 (Hotwords)</h3>
                                    <p class="text-sm text-text-muted mt-1">
                                        添加项目特定的专业术语，以提高语音转录的准确性。
                                        <a href="https://help.aliyun.com/zh/model-studio/custom-hot-words" target="_blank" class="text-primary hover:underline">了解更多</a>
                                    </p>
                                </div>
                                <button @click="addHotword" class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-800 text-sm font-medium transition-colors">
                                    <span class="material-symbols-outlined text-[18px]">add</span>
                                    添加词条
                                </button>
                            </div>

                            <div class="border border-border-light dark:border-border-dark rounded-lg overflow-hidden">
                                <div class="grid grid-cols-12 gap-4 px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-border-light dark:border-border-dark text-xs font-semibold text-text-muted">
                                    <div class="col-span-6">术语文本</div>
                                    <div class="col-span-2">权重 (1-5)</div>
                                    <div class="col-span-2">语言</div>
                                    <div class="col-span-2 text-right">操作</div>
                                </div>
                                
                                <div v-if="hotwords.length === 0" class="p-8 text-center text-text-muted text-sm">
                                    暂无自定义术语
                                </div>

                                <div v-for="(word, index) in hotwords" :key="index" class="grid grid-cols-12 gap-4 px-4 py-3 items-center border-b border-border-light dark:border-border-dark last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                                    <div class="col-span-6">
                                        <input v-model="word.text" type="text" placeholder="输入术语 (如: MeetMind)" class="w-full px-3 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-transparent text-sm focus:ring-1 focus:ring-primary focus:border-primary">
                                    </div>
                                    <div class="col-span-2">
                                         <input v-model.number="word.weight" type="number" min="1" max="5" class="w-full px-3 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-transparent text-sm focus:ring-1 focus:ring-primary focus:border-primary">
                                    </div>
                                    <div class="col-span-2">
                                        <select v-model="word.lang" class="w-full px-3 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-transparent text-sm focus:ring-1 focus:ring-primary focus:border-primary">
                                            <option value="zh">中文</option>
                                            <option value="en">English</option>
                                        </select>
                                    </div>
                                    <div class="col-span-2 text-right">
                                        <button @click="removeHotword(index)" class="text-gray-400 hover:text-red-500 transition-colors p-1">
                                            <span class="material-symbols-outlined text-[18px]">delete</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- CHAT VIEW -->
                <div v-show="activeTab === 'chat'" class="flex-1 min-h-0 flex flex-col lg:flex-row gap-6 animate-in fade-in duration-300 relative">
                    <!-- Chat Sidebar (History) -->
                    <div class="w-full lg:w-64 shrink-0 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-2 flex flex-col gap-1 h-full max-h-[calc(100vh-160px)]">
                        <button 
                            @click="createNewSession" 
                            class="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-primary hover:bg-primary/5 transition-colors text-left mb-2 border border-dashed border-primary/30"
                        >
                            <span class="material-symbols-outlined text-[20px]">add_comment</span>
                            新对话
                        </button>

                        <div class="flex-1 overflow-y-auto space-y-1">
                            <div v-if="chatSessions.length === 0" class="text-xs text-text-muted text-center py-4">
                                暂无历史会话
                            </div>
                            <button 
                                v-for="session in chatSessions" 
                                :key="session.id"
                                @click="loadSessionMessages(session.id)"
                                class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors text-left group"
                                :class="currentSessionId === session.id ? 'bg-primary/10 text-primary font-medium' : 'text-text-main dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
                            >
                                <span class="material-symbols-outlined text-[18px]" :class="currentSessionId === session.id ? 'text-primary' : 'text-gray-400'">chat_bubble_outline</span>
                                <span class="truncate">{{ session.title }}</span>
                            </button>
                        </div>
                    </div>

                    <!-- Chat Area -->
                    <div class="flex-1 flex flex-col h-full min-w-0">
                        <div class="flex-1 overflow-y-auto p-3 space-y-4 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-inner mb-2" ref="chatContainer">
                            
                            <!-- Welcome Message -->
                            <div v-if="chatMessages.length === 0" class="flex flex-col items-center justify-center h-full text-text-muted">
                                <div class="size-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                                    <span class="material-symbols-outlined text-4xl text-primary">chat_spark</span>
                                </div>
                                <h3 class="text-lg font-bold text-text-main dark:text-white">项目智能问答</h3>
                                <p class="text-sm max-w-sm text-center mt-2">我可以基于项目知识库和会议纪要回答您的问题。试着问我："这个项目的核心目标是什么？" 或 "上周的会议讨论了什么？"</p>
                            </div>

                            <!-- Messages -->
                            <div v-for="(msg, index) in chatMessages" :key="index" class="flex flex-col gap-2">
                                <!-- User Message -->
                                <div v-if="msg.role === 'user'" class="flex justify-end">
                                    <div class="bg-primary text-white px-4 py-2.5 rounded-2xl rounded-tr-sm max-w-[80%] shadow-md text-sm">
                                        {{ msg.content }}
                                    </div>
                                </div>

                                <!-- Assistant Message -->
                                <div v-else class="flex gap-3 max-w-[90%]">
                                    <div class="size-8 rounded-full bg-teal-600 text-white flex items-center justify-center shrink-0 mt-1 shadow-sm">
                                        <span class="material-symbols-outlined text-[18px]">smart_toy</span>
                                    </div>
                                    <div class="flex flex-col gap-2 w-full min-w-0">
                                        
                                        <!-- Thoughts / Actions -->
                                        <div v-if="msg.isStreaming && msg.thoughts && msg.thoughts.length > 0" class="flex flex-col gap-2">
                                            <div v-for="(thought, tIdx) in msg.thoughts" :key="tIdx" class="bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700 rounded-lg p-3 text-xs text-gray-500 dark:text-gray-400 font-mono">
                                                <div class="flex items-center gap-2 mb-1 text-gray-400">
                                                    <span class="material-symbols-outlined text-[14px]">psychology</span>
                                                    <span class="uppercase tracking-wider text-[10px]">Thinking Process</span>
                                                </div>
                                                {{ thought }}
                                            </div>
                                        </div>

                                        <!-- Actions -->
                                        <div v-if="msg.actions && msg.actions.length > 0" class="flex flex-col gap-1">
                                            <div v-for="(action, aIdx) in msg.actions" :key="aIdx" class="flex items-center gap-2 text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-3 py-1.5 rounded-md w-fit">
                                                <span class="material-symbols-outlined text-[14px] animate-pulse">travel_explore</span>
                                                <span>Searching: "{{ action.query }}"</span>
                                            </div>
                                        </div>

                                        <!-- Content -->
                                        <div v-if="msg.content" class="bg-white dark:bg-surface-dark border border-gray-100 dark:border-gray-700 rounded-2xl rounded-tl-sm p-4 shadow-sm text-sm text-text-main dark:text-gray-200" @click="handleMessageClick">
                                            <div class="prose dark:prose-invert max-w-none prose-sm" v-html="renderMessage(msg.content)"></div>
                                        </div>
                                        
                                        <!-- Loading Indicator -->
                                        <div v-if="msg.isStreaming && !msg.content" class="flex items-center gap-2 text-xs text-gray-400 mt-1 pl-1">
                                            <span class="size-2 bg-gray-400 rounded-full animate-bounce"></span>
                                            <span class="size-2 bg-gray-400 rounded-full animate-bounce delay-75"></span>
                                            <span class="size-2 bg-gray-400 rounded-full animate-bounce delay-150"></span>
                                        </div>

                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Input Area -->
                        <div class="mt-auto bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-2 flex gap-2 items-end shadow-sm relative sticky bottom-0 z-10">
                            <textarea 
                                v-model="chatInput"
                                @keydown.enter.prevent="sendChatMessage"
                                placeholder="询问关于项目的问题..."
                                class="flex-1 bg-transparent border-none focus:ring-0 text-sm p-2 resize-none max-h-32 min-h-[44px] text-text-main dark:text-white placeholder:text-text-muted"
                                rows="1"
                            ></textarea>
                            <button 
                                @click="sendChatMessage" 
                                :disabled="!chatInput.trim() || isChatting"
                                class="flex items-center justify-center p-2 rounded-lg bg-primary hover:bg-primary-hover text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors mb-0.5"
                            >
                                <span class="material-symbols-outlined text-[20px]">{{ isChatting ? 'stop_circle' : 'send' }}</span>
                            </button>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </main>

    <!-- Select Minutes Modal -->
    <el-dialog v-model="showSelectMinutesModal" title="选择参考资料" width="600px" align-center class="rounded-xl">
        <div class="flex flex-col gap-4">
            <p class="text-sm text-text-muted">请选择用于生成知识库的资料。系统将根据选中的内容进行分析。</p>
            
            <div class="max-h-[400px] overflow-y-auto border border-border-light dark:border-border-dark rounded-lg divide-y divide-border-light dark:divide-border-dark">
                <!-- Meetings -->
                <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800/50 font-bold text-xs text-text-muted uppercase tracking-wider">会议纪要</div>
                <div v-if="availableMinutes.length === 0" class="p-4 text-center text-text-muted text-sm">
                    暂无已生成的会议纪要。
                </div>
                <div v-for="r in availableMinutes" :key="'m'+r.id" class="p-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-3">
                    <input type="checkbox" :value="r.minutes_id" v-model="selectedMinutesIds" class="rounded border-gray-300 text-primary focus:ring-primary size-4">
                    <div class="flex flex-col">
                        <span class="font-medium text-text-main dark:text-white text-sm">{{ r.filename }}</span>
                        <span class="text-xs text-text-muted">{{ new Date(r.created_at).toLocaleString() }}</span>
                    </div>
                    <span class="ml-auto text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">已生成纪要</span>
                </div>

                <!-- Documents -->
                <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800/50 font-bold text-xs text-text-muted uppercase tracking-wider border-t border-border-light dark:border-border-dark">项目文档</div>
                <div v-if="documents.length === 0" class="p-4 text-center text-text-muted text-sm">
                    暂无项目文档。
                </div>
                <div v-for="d in documents" :key="'d'+d.id" class="p-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-3">
                    <input type="checkbox" :value="d.id" v-model="selectedDocumentIds" class="rounded border-gray-300 text-primary focus:ring-primary size-4">
                    <div class="flex flex-col">
                        <span class="font-medium text-text-main dark:text-white text-sm">{{ d.filename }}</span>
                        <span class="text-xs text-text-muted">{{ new Date(d.created_at).toLocaleString() }} • {{ d.file_type }}</span>
                    </div>
                    <span class="ml-auto text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">已上传</span>
                </div>
            </div>
        </div>
        <template #footer>
            <div class="flex justify-end gap-3">
                <button @click="showSelectMinutesModal = false" class="px-4 py-2 rounded-lg border border-border-light dark:border-border-dark text-text-main hover:bg-gray-50 text-sm font-medium">取消</button>
                <button @click="confirmGenerate" class="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-white text-sm font-bold shadow-sm disabled:opacity-50 disabled:cursor-not-allowed" :disabled="availableMinutes.length === 0 && documents.length === 0">
                    确认生成
                </button>
            </div>
        </template>
    </el-dialog>

    <el-dialog v-model="showResearchModal" title="Deep Research in Progress" width="500px" align-center :close-on-click-modal="false" :show-close="false" class="rounded-xl">
        <div class="flex flex-col items-center justify-center py-8 gap-6">
            <div class="relative size-16">
                 <span class="material-symbols-outlined text-6xl text-primary animate-pulse">psychology</span>
            </div>
            <div class="text-center">
                <h3 class="text-lg font-bold text-text-main dark:text-white mb-2">AI is researching...</h3>
                <p class="text-text-muted text-sm px-4 animate-pulse">{{ researchStatusMessage }}</p>
            </div>
        </div>
    </el-dialog>

  </div>
</template>

<style scoped>
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
  border-radius: 0.75rem;
}
:deep(.el-upload-dragger:hover) {
  border: none;
}
:deep(.el-upload-dragger.is-dragover) {
  background-color: transparent;
}
</style>
