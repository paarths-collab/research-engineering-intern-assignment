const path = require('path');
/** @type {import('next').NextConfig} */
const { resolveBackendOrigin } = require('./lib/deploymentConfig.cjs');
const { backendOrigin: deploymentOrigin } = require('./deployment.json');
const backendOrigin = resolveBackendOrigin(process.env, deploymentOrigin);

const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["cesium", "resium", "@react-three/fiber", "@react-three/drei", "three"],
  outputFileTracingRoot: path.join(__dirname, '../'),
  images: {
    qualities: [75, 95],
  },
  env: {
    CESIUM_BASE_URL: "https://cesium.com/downloads/cesiumjs/releases/1.114/Build/Cesium",
  },
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...(config.resolve.fallback || {}),
        fs: false,
        path: false,
      };
    }
    return config;
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/glbe",
        destination: "/globe",
        permanent: false,
      },
    ];
  },
};

module.exports = nextConfig;