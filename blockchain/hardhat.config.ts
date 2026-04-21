import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import "dotenv/config";

// Optional: populate these in .env to enable Sepolia deployment
const SEPOLIA_RPC_URL = process.env.SEPOLIA_RPC_URL ?? "";
const OPERATOR_PRIVATE_KEY = process.env.OPERATOR_PRIVATE_KEY ?? "";
const ETHERSCAN_API_KEY = process.env.ETHERSCAN_API_KEY ?? "";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    // Default: local Hardhat node — start with: npm run node
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    hardhat: {
      chainId: 31337,
    },
    // Optional: Sepolia testnet — set SEPOLIA_RPC_URL and OPERATOR_PRIVATE_KEY in .env
    ...(SEPOLIA_RPC_URL && OPERATOR_PRIVATE_KEY
      ? {
          sepolia: {
            url: SEPOLIA_RPC_URL,
            accounts: [OPERATOR_PRIVATE_KEY],
            chainId: 11155111,
          },
        }
      : {}),
  },
  // Optional: Etherscan verification — set ETHERSCAN_API_KEY in .env
  ...(ETHERSCAN_API_KEY
    ? {
        etherscan: {
          apiKey: ETHERSCAN_API_KEY,
        },
      }
    : {}),
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};

export default config;
