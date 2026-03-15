/** @type {import('next').NextConfig} */
const backendOrigin = (
  process.env.NEXT_PUBLIC_API_URL
  || process.env.NEXT_PUBLIC_API_BASE_URL
  || process.env.BACKEND_API_URL
  || "https://research-engineering-intern-assignment-zq0i.onrender.com"
).replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["cesium", "resium"],
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