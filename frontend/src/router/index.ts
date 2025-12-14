import { createRouter, createWebHistory } from 'vue-router'
import ProjectList from '../views/ProjectList.vue'
import ProjectDetail from '../views/ProjectDetail.vue'
import TranscriptionView from '../views/TranscriptionView.vue'
import MinutesView from '../views/MinutesView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: ProjectList
    },
    {
      path: '/project/:id',
      name: 'project-detail',
      component: ProjectDetail
    },
    {
      path: '/recording/:id',
      name: 'transcription',
      component: TranscriptionView
    },
    {
      path: '/recording/:id/minutes',
      name: 'minutes',
      component: MinutesView
    }
  ]
})

export default router
