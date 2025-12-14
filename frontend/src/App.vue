<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="bg-background-light dark:bg-background-dark font-sans text-text-main dark:text-gray-100 min-h-screen flex flex-col overflow-x-hidden antialiased selection:bg-primary/10 selection:text-primary">
    <RouterView />
  </div>
</template>
