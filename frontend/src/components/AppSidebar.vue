<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

const props = defineProps<{
  projectName?: string;
  projectId?: string | number;
  defaultCollapsed?: boolean;
}>();

const user = {
  name: 'Admin User',
  avatar: 'https://ui-avatars.com/api/?name=Admin+User&background=0D9488&color=fff'
};

const isCollapsed = ref(props.defaultCollapsed || false);

const menuItems = computed(() => [
  { 
    id: 'home', 
    label: '首页', 
    icon: 'home', 
    path: '/' 
  },
  {
    id: 'project',
    label: '项目',
    icon: 'folder',
    children: [
      { id: 'settings', label: '项目设置', icon: 'settings', path: `/project/${props.projectId}/settings` }, // Placeholder path
      { id: 'files', label: '文件列表', icon: 'description', path: `/project/${props.projectId}` },
      { id: 'kb', label: '项目知识库', icon: 'auto_stories', path: `/project/${props.projectId}/knowledge-base` },
      { id: 'chat', label: '项目问答', icon: 'chat', path: `/project/${props.projectId}/chat` }
    ]
  }
]);

const isActive = (path: string) => {
  // Simple active check, can be enhanced
  if (path === '/') return route.path === '/';
  if (path.includes('knowledge-base')) return route.path.includes('knowledge-base') || (route.query.tab === 'kb');
  if (path.includes('settings')) return route.path.includes('settings') || (route.query.tab === 'settings');
  if (path.includes('chat')) return route.path.includes('chat') || (route.query.tab === 'chat');
  if (path.endsWith(`/${props.projectId}`)) return route.path === `/project/${props.projectId}` && (!route.query.tab || route.query.tab === 'files');
  return route.path === path;
};

const navigate = (path: string) => {
  if (path.includes('knowledge-base')) {
      router.push({ path: `/project/${props.projectId}`, query: { tab: 'kb' } });
  } else if (path.includes('settings')) {
      router.push({ path: `/project/${props.projectId}`, query: { tab: 'settings' } });
  } else if (path.includes('chat')) {
      router.push({ path: `/project/${props.projectId}`, query: { tab: 'chat' } });
  } else if (path.endsWith(`/${props.projectId}`)) {
      router.push({ path: `/project/${props.projectId}`, query: { tab: 'files' } });
  } else {
      router.push(path);
  }
};
</script>

<template>
  <aside 
    class="bg-surface-light dark:bg-surface-dark border-r border-border-light dark:border-border-dark flex flex-col h-screen sticky top-0 transition-all duration-300 ease-in-out"
    :class="isCollapsed ? 'w-20' : 'w-64'"
  >
    <!-- Logo Area -->
    <div class="h-16 flex items-center gap-3 px-6 border-b border-border-light dark:border-border-dark cursor-pointer overflow-hidden whitespace-nowrap" @click="router.push('/')">
        <div class="size-8 text-primary dark:text-white flex items-center justify-center rounded-lg bg-primary/5 dark:bg-white/10 shrink-0">
          <span class="material-symbols-outlined text-[20px]">graphic_eq</span>
        </div>
        <h2 
            class="text-base font-bold tracking-tight text-text-main dark:text-white transition-opacity duration-300"
            :class="isCollapsed ? 'opacity-0 w-0' : 'opacity-100'"
        >
            MeetMind
        </h2>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 overflow-y-auto py-6 px-3 flex flex-col gap-1 overflow-x-hidden">
      <template v-for="item in menuItems" :key="item.id">
        <div v-if="!item.children">
            <button 
                @click="navigate(item.path)"
                class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
                :class="[
                    isActive(item.path) ? 'bg-primary/10 text-primary' : 'text-text-muted hover:text-text-main hover:bg-gray-100 dark:hover:bg-gray-800',
                    isCollapsed ? 'justify-center px-0' : ''
                ]"
                :title="isCollapsed ? item.label : ''"
            >
                <span class="material-symbols-outlined text-[20px] shrink-0">{{ item.icon }}</span>
                <span :class="isCollapsed ? 'hidden' : 'block'">{{ item.label }}</span>
            </button>
        </div>
        <div v-else class="flex flex-col gap-1 mt-2">
            <div 
                class="px-3 text-xs font-semibold text-text-muted uppercase tracking-wider mb-1 transition-opacity duration-300 whitespace-nowrap overflow-hidden"
                :class="isCollapsed ? 'opacity-0 h-0 mb-0' : 'opacity-100'"
            >
                {{ item.label }}
            </div>
            <button 
                v-for="child in item.children"
                :key="child.id"
                @click="navigate(child.path)"
                class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
                :class="[
                    isActive(child.path) ? 'bg-primary/10 text-primary' : 'text-text-muted hover:text-text-main hover:bg-gray-100 dark:hover:bg-gray-800',
                    isCollapsed ? 'justify-center px-0' : ''
                ]"
                :title="isCollapsed ? child.label : ''"
            >
                <span class="material-symbols-outlined text-[20px] shrink-0">{{ child.icon }}</span>
                <span :class="isCollapsed ? 'hidden' : 'block'">{{ child.label }}</span>
            </button>
        </div>
      </template>
    </nav>

    <!-- Footer -->
    <div 
        class="p-4 border-t border-border-light dark:border-border-dark flex"
        :class="isCollapsed ? 'flex-col items-center gap-4' : 'items-center justify-between'"
    >
        <!-- User Info -->
        <div class="flex items-center gap-3 overflow-hidden">
             <img :src="user.avatar" alt="User" class="size-8 rounded-full shrink-0">
             <div class="flex flex-col min-w-0" v-show="!isCollapsed">
                 <span class="text-sm font-medium text-text-main dark:text-white truncate">{{ user.name }}</span>
             </div>
        </div>

        <!-- Collapse Button -->
        <button 
            @click="isCollapsed = !isCollapsed"
            class="flex items-center justify-center p-2 rounded-lg text-text-muted hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            :title="isCollapsed ? '展开' : '收起'"
        >
            <span class="material-symbols-outlined text-[20px]">
                {{ isCollapsed ? 'last_page' : 'first_page' }}
            </span>
        </button>
    </div>
  </aside>
</template>
