-- CreateTable
CREATE TABLE "OnboardingState" (
    "phone" TEXT NOT NULL,
    "username" TEXT,
    "firstName" TEXT,
    "lastName" TEXT,

    CONSTRAINT "OnboardingState_pkey" PRIMARY KEY ("phone")
);

-- CreateIndex
CREATE UNIQUE INDEX "OnboardingState_username_key" ON "OnboardingState"("username");
