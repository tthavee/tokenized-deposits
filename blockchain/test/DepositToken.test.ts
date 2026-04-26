import { expect } from "chai";
import { ethers, upgrades } from "hardhat";
import { DepositToken } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";
import * as fc from "fast-check";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function deploy(assetType: string, networkLabel: string): Promise<DepositToken> {
  const [owner] = await ethers.getSigners();
  const Factory = await ethers.getContractFactory("DepositToken");
  const proxy = await upgrades.deployProxy(
    Factory,
    [assetType, networkLabel, owner.address],
    { kind: "uups" }
  );
  await proxy.waitForDeployment();
  return proxy as unknown as DepositToken;
}

// ---------------------------------------------------------------------------
// Unit Tests
// ---------------------------------------------------------------------------
describe("DepositToken — unit tests", () => {
  let owner: HardhatEthersSigner;
  let user: HardhatEthersSigner;
  let other: HardhatEthersSigner;
  let usd: DepositToken;
  let eur: DepositToken;

  beforeEach(async () => {
    [owner, user, other] = await ethers.getSigners();
    usd = await deploy("USD", "hardhat");
    eur = await deploy("EUR", "hardhat");
  });

  // ── Deployment ────────────────────────────────────────────────────────────
  describe("deployment", () => {
    it("sets owner correctly", async () => {
      expect(await usd.owner()).to.equal(owner.address);
    });

    it("stores assetType and networkLabel", async () => {
      expect(await usd.assetType()).to.equal("USD");
      expect(await usd.networkLabel()).to.equal("hardhat");
    });

    it("has zero total supply initially", async () => {
      expect(await usd.totalSupply()).to.equal(0n);
    });
  });

  // ── KYC allowlist ─────────────────────────────────────────────────────────
  describe("registerWallet / revokeWallet", () => {
    it("registers a wallet and isApproved returns true", async () => {
      await usd.registerWallet(user.address);
      expect(await usd.isApproved(user.address)).to.be.true;
    });

    it("emits WalletRegistered event", async () => {
      await expect(usd.registerWallet(user.address))
        .to.emit(usd, "WalletRegistered")
        .withArgs(user.address);
    });

    it("revokes a wallet and isApproved returns false", async () => {
      await usd.registerWallet(user.address);
      await usd.revokeWallet(user.address);
      expect(await usd.isApproved(user.address)).to.be.false;
    });

    it("emits WalletRevoked event", async () => {
      await usd.registerWallet(user.address);
      await expect(usd.revokeWallet(user.address))
        .to.emit(usd, "WalletRevoked")
        .withArgs(user.address);
    });

    it("reverts registerWallet from non-owner", async () => {
      await expect(
        usd.connect(user).registerWallet(other.address)
      ).to.be.revertedWithCustomError(usd, "OwnableUnauthorizedAccount");
    });

    it("reverts revokeWallet from non-owner", async () => {
      await usd.registerWallet(user.address);
      await expect(
        usd.connect(user).revokeWallet(user.address)
      ).to.be.revertedWithCustomError(usd, "OwnableUnauthorizedAccount");
    });
  });

  // ── Mint ──────────────────────────────────────────────────────────────────
  describe("mint", () => {
    const AMOUNT = ethers.parseUnits("100", 18);

    beforeEach(async () => {
      await usd.registerWallet(user.address);
    });

    it("mints to an approved wallet and updates balance", async () => {
      await usd.mint(user.address, AMOUNT);
      expect(await usd.balanceOf(user.address)).to.equal(AMOUNT);
    });

    it("increases totalSupply", async () => {
      await usd.mint(user.address, AMOUNT);
      expect(await usd.totalSupply()).to.equal(AMOUNT);
    });

    it("reverts mint to non-approved wallet", async () => {
      await expect(
        usd.mint(other.address, AMOUNT)
      ).to.be.revertedWithCustomError(usd, "WalletNotApproved");
    });

    it("reverts mint when paused", async () => {
      await usd.pause();
      await expect(
        usd.mint(user.address, AMOUNT)
      ).to.be.revertedWithCustomError(usd, "EnforcedPause");
    });

    it("emits Mint event with correct args", async () => {
      await expect(usd.mint(user.address, AMOUNT))
        .to.emit(usd, "Mint")
        .withArgs(user.address, AMOUNT);
    });
  });

  // ── Burn ──────────────────────────────────────────────────────────────────
  describe("burn", () => {
    const AMOUNT = ethers.parseUnits("50", 18);

    beforeEach(async () => {
      await usd.registerWallet(user.address);
      await usd.mint(user.address, AMOUNT);
    });

    it("burns from an approved wallet and reduces balance", async () => {
      await usd.burn(user.address, AMOUNT);
      expect(await usd.balanceOf(user.address)).to.equal(0n);
    });

    it("reduces totalSupply", async () => {
      await usd.burn(user.address, AMOUNT);
      expect(await usd.totalSupply()).to.equal(0n);
    });

    it("reverts burn from non-approved wallet", async () => {
      await usd.revokeWallet(user.address);
      await expect(
        usd.burn(user.address, AMOUNT)
      ).to.be.revertedWithCustomError(usd, "WalletNotApproved");
    });

    it("reverts burn when paused", async () => {
      await usd.pause();
      await expect(
        usd.burn(user.address, AMOUNT)
      ).to.be.revertedWithCustomError(usd, "EnforcedPause");
    });

    it("emits Burn event with correct args", async () => {
      await expect(usd.burn(user.address, AMOUNT))
        .to.emit(usd, "Burn")
        .withArgs(user.address, AMOUNT);
    });
  });

  // ── Pause / unpause ───────────────────────────────────────────────────────
  describe("pause / unpause", () => {
    it("owner can pause and unpause", async () => {
      await usd.pause();
      expect(await usd.paused()).to.be.true;
      await usd.unpause();
      expect(await usd.paused()).to.be.false;
    });

    it("pausing USD does not affect EUR", async () => {
      const AMOUNT = ethers.parseUnits("10", 18);
      await eur.registerWallet(user.address);
      await usd.pause();
      // EUR contract is unaffected
      await expect(eur.mint(user.address, AMOUNT)).not.to.be.reverted;
      expect(await eur.balanceOf(user.address)).to.equal(AMOUNT);
    });

    it("reverts pause from non-owner", async () => {
      await expect(
        usd.connect(user).pause()
      ).to.be.revertedWithCustomError(usd, "OwnableUnauthorizedAccount");
    });
  });

  // ── ERC-20 interface ──────────────────────────────────────────────────────
  describe("ERC-20 interface", () => {
    const AMOUNT = ethers.parseUnits("200", 18);

    beforeEach(async () => {
      await usd.registerWallet(user.address);
      await usd.registerWallet(other.address);
      await usd.mint(user.address, AMOUNT);
    });

    it("balanceOf returns correct balance", async () => {
      expect(await usd.balanceOf(user.address)).to.equal(AMOUNT);
    });

    it("totalSupply reflects minted tokens", async () => {
      expect(await usd.totalSupply()).to.equal(AMOUNT);
    });

    it("transfer moves tokens between addresses", async () => {
      const HALF = AMOUNT / 2n;
      await usd.connect(user).transfer(other.address, HALF);
      expect(await usd.balanceOf(user.address)).to.equal(HALF);
      expect(await usd.balanceOf(other.address)).to.equal(HALF);
    });
  });

  // ── Independence of contracts ─────────────────────────────────────────────
  describe("contract independence", () => {
    it("USD and EUR contracts have independent state", async () => {
      const AMOUNT = ethers.parseUnits("100", 18);
      await usd.registerWallet(user.address);
      await usd.mint(user.address, AMOUNT);

      // EUR contract should have zero balance for user
      expect(await eur.balanceOf(user.address)).to.equal(0n);
      expect(await usd.totalSupply()).to.equal(AMOUNT);
      expect(await eur.totalSupply()).to.equal(0n);
    });
  });
});

// ---------------------------------------------------------------------------
// Property-Based Tests
// ---------------------------------------------------------------------------
describe("DepositToken — property-based tests", () => {
  let user: HardhatEthersSigner;
  let nonOwner: HardhatEthersSigner;

  before(async () => {
    [, user, nonOwner] = await ethers.getSigners();
  });

  const ITERATIONS = 100;

  // P3: For any non-allowlisted address, mint reverts on any (Asset_Type, Network) contract
  it(
    "// Feature: tokenized-deposits-poc, Property 3: mint always reverts for non-allowlisted wallets",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.tuple(fc.string({ minLength: 1, maxLength: 8 }), fc.string({ minLength: 1, maxLength: 8 })),
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async ([assetType, networkLabel], amount) => {
            const contract = await deploy(assetType, networkLabel);
            await expect(
              contract.mint(user.address, amount)
            ).to.be.revertedWithCustomError(contract, "WalletNotApproved");
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P5: For any approved wallet and amount N, balance increases by N; other contracts unchanged
  it(
    "// Feature: tokenized-deposits-poc, Property 5: mint increases balance by exact amount; other contracts unaffected",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const usd = await deploy("USD", "hardhat");
            const eur = await deploy("EUR", "hardhat");
            await usd.registerWallet(user.address);

            const before = await usd.balanceOf(user.address);
            await usd.mint(user.address, amount);
            const after = await usd.balanceOf(user.address);

            expect(after - before).to.equal(amount);
            // EUR contract unaffected
            expect(await eur.balanceOf(user.address)).to.equal(0n);
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P9: For any mint call, Mint event contains correct address and amount
  it(
    "// Feature: tokenized-deposits-poc, Property 9: Mint event always contains correct recipient and amount",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const contract = await deploy("USD", "hardhat");
            await contract.registerWallet(user.address);
            await expect(contract.mint(user.address, amount))
              .to.emit(contract, "Mint")
              .withArgs(user.address, amount);
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P11: For any wallet with balance >= N, balance decreases by N; other contracts unchanged
  it(
    "// Feature: tokenized-deposits-poc, Property 11: burn decreases balance by exact amount; other contracts unaffected",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const usd = await deploy("USD", "hardhat");
            const eur = await deploy("EUR", "hardhat");
            await usd.registerWallet(user.address);
            await usd.mint(user.address, amount);

            const before = await usd.balanceOf(user.address);
            await usd.burn(user.address, amount);
            const after = await usd.balanceOf(user.address);

            expect(before - after).to.equal(amount);
            // EUR contract unaffected
            expect(await eur.balanceOf(user.address)).to.equal(0n);
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P14: For any burn call, Burn event contains correct address and amount
  it(
    "// Feature: tokenized-deposits-poc, Property 14: Burn event always contains correct source and amount",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const contract = await deploy("USD", "hardhat");
            await contract.registerWallet(user.address);
            await contract.mint(user.address, amount);
            await expect(contract.burn(user.address, amount))
              .to.emit(contract, "Burn")
              .withArgs(user.address, amount);
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P18: For any non-owner address, privileged calls revert
  it(
    "// Feature: tokenized-deposits-poc, Property 18: all privileged calls revert for non-owner",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const contract = await deploy("USD", "hardhat");
            const asNonOwner = contract.connect(nonOwner);

            await expect(
              asNonOwner.registerWallet(user.address)
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

            await expect(
              asNonOwner.revokeWallet(user.address)
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

            await expect(
              asNonOwner.mint(user.address, amount)
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

            await expect(
              asNonOwner.burn(user.address, amount)
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

            await expect(
              asNonOwner.pause()
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");

            await expect(
              asNonOwner.unpause()
            ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );

  // P19: Pause then unpause for a given (Asset_Type, Network) is a round trip; other pairs unaffected
  it(
    "// Feature: tokenized-deposits-poc, Property 19: pause/unpause is a round trip; other contracts unaffected",
    async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.bigInt({ min: 1n, max: ethers.parseUnits("1000000", 18) }),
          async (amount) => {
            const usd = await deploy("USD", "hardhat");
            const eur = await deploy("EUR", "hardhat");
            await usd.registerWallet(user.address);
            await eur.registerWallet(user.address);

            // Pause USD
            await usd.pause();
            expect(await usd.paused()).to.be.true;

            // EUR unaffected — can still mint
            await expect(eur.mint(user.address, amount)).not.to.be.reverted;

            // Unpause USD — round trip
            await usd.unpause();
            expect(await usd.paused()).to.be.false;

            // USD can mint again
            await expect(usd.mint(user.address, amount)).not.to.be.reverted;
          }
        ),
        { numRuns: ITERATIONS }
      );
    }
  );
});
