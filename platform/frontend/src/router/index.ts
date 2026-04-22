import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue')
      },
      {
        path: '/domains',
        name: 'domains',
        component: () => import('@/views/DomainView.vue')
      }
    ]
  }
]

export default createRouter({
  history: createWebHistory(),
  routes
})
