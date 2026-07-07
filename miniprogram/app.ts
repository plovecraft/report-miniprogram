import { CLOUDBASE_ENV_ID } from './config'

App<IAppOption>({
  globalData: {},
  onLaunch() {
    if (CLOUDBASE_ENV_ID && wx.cloud) {
      wx.cloud.init({
        env: CLOUDBASE_ENV_ID,
        traceUser: true,
      })
    }
  },
})
