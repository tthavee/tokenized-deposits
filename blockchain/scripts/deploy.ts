import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

interface DeploymentInfo {
  contractAddress: string;
  deployer: string;
  network: string;
  chainId: string;
  deployedAt: string;
  abi: unknown[];
}

async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying contracts with account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString()
  );

  // Deploy DepositToken for (USD, hardhat) pair — override via env vars for other pairs
  const assetType = process.env.ASSET_TYPE ?? "USD";
  const networkLabel = process.env.NETWORK_LABEL ?? network.name;
  const ContractFactory = await ethers.getContractFactory("DepositToken");
  const contract = await ContractFactory.deploy(assetType, networkLabel);
  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  console.log("DepositToken deployed to:", contractAddress);

  // Save deployment info for the backend to consume
  const artifactPath = path.join(
    __dirname,
    "../artifacts/contracts/DepositToken.sol/DepositToken.json"
  );
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  const deploymentInfo: DeploymentInfo = {
    contractAddress,
    deployer: deployer.address,
    network: network.name,
    chainId: (await ethers.provider.getNetwork()).chainId.toString(),
    deployedAt: new Date().toISOString(),
    abi: artifact.abi,
  };

  const outputPath = path.join(__dirname, "../deployment.json");
  fs.writeFileSync(outputPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("Deployment info saved to:", outputPath);
}

main()
  .then(() => process.exit(0))
  .catch((error: Error) => {
    console.error(error);
    process.exit(1);
  });
